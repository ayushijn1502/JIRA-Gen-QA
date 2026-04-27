"""
CLI Entry Point -- the "front door" of AutoTest-Agent.

This is the file you run.  It uses Typer to create a command-line interface
with two commands:

  autotest run PROJ-123    -- Generate tests for a JIRA ticket end-to-end.
  autotest index           -- (Re)build the RAG index of the target framework.

Under the hood it:
1. Reads config.yaml to get API keys and settings.
2. Reads the docs/*.md files to build agent personas.
3. Creates all the infrastructure services (JIRA, RAG, LLM, GitHub, pytest).
4. Wires them into the LangGraph state machine.
5. Kicks off the workflow.

Usage:
    python main.py run PROJ-123
    python main.py index
"""

from __future__ import annotations

import typer
from rich.console import Console

from autotest_agent.agents.graph import build_graph
from autotest_agent.agents.nodes import NodeContainer
from autotest_agent.agents.prompts import PromptBuilder
from autotest_agent.config import load_settings
from autotest_agent.infrastructure.gemini_preflight import preflight_gemini
from autotest_agent.infrastructure.github_service import GitHubService, SkippedGitHubService
from autotest_agent.infrastructure.jira_wrapper import JiraWrapper
from autotest_agent.infrastructure.llm_service import GeminiLLMService
from autotest_agent.infrastructure.rag_engine import RAGEngine
from autotest_agent.infrastructure.test_runner import PytestRunner

app = typer.Typer(
    name="autotest",
    help="AutoTest-Agent: generate pytest tests from JIRA tickets using AI.",
    add_completion=False,
)
console = Console()


def _build_services(config_path: str = "config.yaml") -> tuple:
    """
    Load config, create every infrastructure service, and return
    them as a tuple.  This is the "wiring" step -- the only place
    in the codebase where concrete classes meet.
    """
    settings = load_settings(config_path)

    jira = JiraWrapper(
        url=settings.jira.url,
        email=settings.jira.email,
        api_token=settings.jira.api_token,
    )

    rag = RAGEngine(
        embedding_model=settings.rag.embedding_model,
        chunk_size=settings.rag.chunk_size,
        chunk_overlap=settings.rag.chunk_overlap,
        top_k=settings.rag.top_k,
    )

    llm = GeminiLLMService(
        api_key=settings.gemini.api_key,
        model_name=settings.gemini.model_name,
        max_output_tokens=settings.gemini.max_output_tokens,
        max_total_tokens_per_run=settings.gemini.max_total_tokens_per_run,
    )

    skip_github = not settings.github.enabled
    if settings.github.enabled:
        git = GitHubService(
            token=settings.github.token,
            repo=settings.github.repo,
            base_branch=settings.github.base_branch,
        )
    else:
        git = SkippedGitHubService()

    runner = PytestRunner()
    prompts = PromptBuilder(docs_path=settings.docs_path)

    return settings, jira, rag, llm, git, runner, prompts, skip_github


@app.command()
def run(
    ticket_id: str = typer.Argument(help="JIRA ticket ID, e.g. PROJ-123"),
    config: str = typer.Option("config.yaml", "--config", "-c", help="Path to config.yaml"),
) -> None:
    """
    Run the full test-generation pipeline for a JIRA ticket.

    Steps: Fetch JIRA ticket -> Analyze -> Generate -> Verify (pytest)
    -> Approve -> optional GitHub PR (see config github.enabled).
    """
    console.print("[bold]AutoTest-Agent starting...[/bold]\n")

    settings, jira, rag, llm, git, runner, prompts, skip_github = _build_services(config)

    if settings.gemini.run_preflight:
        console.print("[blue]Checking Gemini API key and model...[/blue]")
        preflight_gemini(settings.gemini.api_key, settings.gemini.model_name)
        console.print("[green]Gemini preflight OK.[/green]\n")
    else:
        console.print("[dim]Gemini preflight skipped (gemini.run_preflight: false).[/dim]\n")

    console.print(
        f"[dim]LLM: gemini ({settings.gemini.model_name}); "
        f"max {settings.poc.max_test_scenarios} scenario(s); "
        f"pytest retries: {settings.max_retries}[/dim]"
    )
    if settings.poc.enabled:
        console.print("[dim]POC: reduced RAG chunks for lower token use[/dim]\n")
    else:
        console.print()

    console.print("[blue]Indexing target framework for RAG...[/blue]")
    rag.index_codebase(settings.target_framework_path)

    console.print(f"[blue]Fetching JIRA ticket {ticket_id}...[/blue]")
    ticket = jira.fetch_ticket(ticket_id)

    container = NodeContainer(
        llm=llm,
        rag=rag,
        git=git,
        test_runner=runner,
        prompt_builder=prompts,
        target_framework_path=settings.target_framework_path,
        skip_github=skip_github,
        poc=settings.poc,
    )
    graph = build_graph(container)

    initial_state = {
        "ticket": ticket,
        "retry_count": 0,
        "max_retries": settings.max_retries,
        "error_history": [],
        "phase": "start",
    }

    console.print("[bold]Launching agent workflow...[/bold]\n")
    final_state = graph.invoke(initial_state)

    if isinstance(llm, GeminiLLMService):
        console.print(
            f"[dim]Gemini cumulative tokens this run (reported): "
            f"{llm.tokens_used_this_run}[/dim]"
        )

    phase = final_state.get("phase", "unknown")
    if phase == "deployed":
        console.print("\n[bold green]Done! PR has been created.[/bold green]")
    elif phase == "deployed_with_failed_tests":
        console.print(
            "\n[bold yellow]Done! PR has been created, but the generated tests still failed.[/bold yellow]"
        )
    elif phase == "completed_local":
        console.print("\n[bold green]Done! Tests generated and saved locally (no PR).[/bold green]")
    elif phase == "completed_local_with_failed_tests":
        console.print(
            "\n[bold yellow]Done! Tests were saved locally, but they still failed after retries.[/bold yellow]"
        )
    elif phase == "cancelled":
        console.print("\n[yellow]Run cancelled by user.[/yellow]")
    elif phase == "failed":
        console.print("\n[bold red]Pipeline failed after max retries.[/bold red]")
    else:
        console.print(f"\n[dim]Pipeline ended in phase: {phase}[/dim]")


@app.command()
def index(
    config: str = typer.Option("config.yaml", "--config", "-c", help="Path to config.yaml"),
) -> None:
    """
    Manually rebuild the RAG index of the target framework.

    Useful after you've added or changed files in target_framework/
    and want the agent to "see" the updates.
    """
    settings = load_settings(config)

    rag = RAGEngine(
        embedding_model=settings.rag.embedding_model,
        chunk_size=settings.rag.chunk_size,
        chunk_overlap=settings.rag.chunk_overlap,
        top_k=settings.rag.top_k,
    )

    console.print(f"[blue]Indexing {settings.target_framework_path}...[/blue]")
    rag.index_codebase(settings.target_framework_path)
    console.print("[bold green]RAG index rebuilt successfully.[/bold green]")


if __name__ == "__main__":
    app()
