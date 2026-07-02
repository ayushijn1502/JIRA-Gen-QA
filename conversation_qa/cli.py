from __future__ import annotations

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from autotest_agent.config import load_settings
from autotest_agent.infrastructure.jira_wrapper import JiraWrapper
from autotest_agent.infrastructure.llm_service import GeminiLLMService
from autotest_agent.infrastructure.rag_engine import RAGEngine
from conversation_qa.assistant import ConversationQAAssistant

app = typer.Typer(help="Conversation QA Assist — prototype CLI")
console = Console()


@app.command()
def chat(
    ticket_id: str = typer.Argument(..., help="JIRA key, e.g. PROJ-123"),
    config_path: str = typer.Option("config.yaml", "--config", "-c"),
    no_rag: bool = typer.Option(False, "--no-rag", help="Skip RAG context"),
) -> None:
    settings = load_settings(config_path)
    jira = JiraWrapper(
        url=settings.jira.url,
        email=settings.jira.email,
        api_token=settings.jira.api_token,
    )
    llm = GeminiLLMService(
        api_key=settings.gemini.api_key,
        model_name=settings.gemini.model_name,
        max_output_tokens=settings.gemini.max_output_tokens,
        max_total_tokens_per_run=settings.gemini.max_total_tokens_per_run,
    )
    rag = None
    if not no_rag:
        rag = RAGEngine(
            embedding_model=settings.rag.embedding_model,
            chunk_size=settings.rag.chunk_size,
            chunk_overlap=settings.rag.chunk_overlap,
            top_k=settings.rag.top_k,
        )

    console.print(Panel(f"Fetching {ticket_id}...", title="Conversation QA Assist"))
    ticket = jira.fetch_ticket(ticket_id)
    if rag is not None:
        rag.index_codebase(settings.target_framework_path)

    assistant = ConversationQAAssistant(llm, rag)
    intro = assistant.start(ticket, rag_query=ticket.title)
    console.print(Markdown(intro))
    console.print("\n[dim]Commands: /help /summary /quit[/dim]\n")

    while True:
        try:
            user_input = console.input("[bold cyan]You>[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\nBye.")
            break
        if not user_input:
            continue
        if user_input == "/quit":
            break
        if user_input == "/help":
            console.print("  /summary — export findings JSON\n  /quit — exit")
            continue
        if user_input == "/summary":
            path = assistant.export_summary()
            console.print(f"[green]Saved:[/green] {path}")
            continue

        reply = assistant.ask(user_input)
        console.print(Panel(Markdown(reply), title="QA Analyst", border_style="green"))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
