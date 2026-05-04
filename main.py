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

import contextlib
import os
from collections.abc import Callable, Iterator
from typing import TextIO

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


def _friendly_error(exc: Exception) -> str:
    text = str(exc).strip()
    lower = text.lower()
    if "gemini" in lower or "google" in lower or "api key" in lower:
        return "Could not reach the AI service. Please check Gemini model and API key settings."
    if "jira" in lower:
        return "Could not read the JIRA ticket. Please check JIRA URL, email, token, and ticket key."
    if "connection" in lower or "timeout" in lower or "proxy" in lower:
        return "A network issue occurred while running the pipeline. Please verify connectivity and proxy."
    if text:
        return text
    return f"Pipeline failed due to an unexpected error ({exc.__class__.__name__})."


@contextlib.contextmanager
def _pipeline_console(
    user_log: Callable[[str, str], None] | None,
    requested_console: Console | None,
) -> Iterator[Console]:
    if user_log is None:
        yield requested_console or Console()
        return
    sink: TextIO | None = None
    try:
        sink = open(os.devnull, "w", encoding="utf-8")
        yield Console(file=sink, force_terminal=False, color_system=None)
    finally:
        if sink is not None:
            sink.close()


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

    has_github_creds = bool(settings.github.token.strip()) and bool(settings.github.repo.strip())
    skip_github = (not settings.github.enabled) or (not has_github_creds)
    if settings.github.enabled and has_github_creds:
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


def execute_run(
    ticket_id: str,
    *,
    config: str = "config.yaml",
    console: Console | None = None,
    text_input: Callable[[str], str] | None = None,
    user_log: Callable[[str, str], None] | None = None,
    on_stage: Callable[[str], None] | None = None,
    on_matrix_csv: Callable[[str], None] | None = None,
) -> str:
    def u(level: str, msg: str) -> None:
        if user_log is not None:
            user_log(level, msg)

    def s(stage_id: str) -> None:
        if on_stage is not None:
            on_stage(stage_id)

    with _pipeline_console(user_log, console) as out:
        try:
            out.print("[bold]AutoTest-Agent starting...[/bold]\n")
            u("INFO", "Starting pipeline.")
            s("started")
            settings, jira, rag, llm, git, runner, prompts, skip_github = _build_services(config)
            u("INFO", "Configuration loaded.")
            s("settings")
            if settings.github.enabled and skip_github:
                u(
                    "WARN",
                    "GitHub is enabled in config, but token/repo is missing. "
                    "Continuing in local-only mode.",
                )

            if settings.gemini.run_preflight:
                out.print("[blue]Checking Gemini API key and model...[/blue]")
                u("INFO", "Checking AI service connection.")
                s("gemini_check")
                preflight_gemini(settings.gemini.api_key, settings.gemini.model_name)
                out.print("[green]Gemini preflight OK.[/green]\n")
                u("SUCCESS", "AI service is reachable.")
            else:
                out.print("[dim]Gemini preflight skipped (gemini.run_preflight: false).[/dim]\n")
                s("gemini_check")

            out.print(
                f"[dim]LLM: gemini ({settings.gemini.model_name}); "
                f"max {settings.poc.max_test_scenarios} scenario(s); "
                f"pytest retries: {settings.max_retries}[/dim]"
            )
            if settings.poc.enabled:
                out.print("[dim]POC: reduced RAG chunks for lower token use[/dim]\n")
            else:
                out.print()

            out.print("[blue]Indexing target framework for RAG...[/blue]")
            u("INFO", "Reading existing framework code for context.")
            s("indexing")
            rag.index_codebase(settings.target_framework_path)
            u("SUCCESS", "Framework context indexed.")

            out.print(f"[blue]Fetching JIRA ticket {ticket_id}...[/blue]")
            u("INFO", f"Reading JIRA ticket {ticket_id}.")
            s("jira_fetch")
            ticket = jira.fetch_ticket(ticket_id)
            u("SUCCESS", f"Loaded ticket {ticket.id}: {ticket.title}")

            container = NodeContainer(
                llm=llm,
                rag=rag,
                git=git,
                test_runner=runner,
                prompt_builder=prompts,
                target_framework_path=settings.target_framework_path,
                skip_github=skip_github,
                poc=settings.poc,
                console=out,
                text_input=text_input,
                user_log=user_log,
                on_stage=on_stage,
                on_matrix_csv=on_matrix_csv,
            )
            graph = build_graph(container)
            initial_state = {
                "ticket": ticket,
                "retry_count": 0,
                "max_retries": settings.max_retries,
                "error_history": [],
                "phase": "start",
            }

            out.print("[bold]Launching agent workflow...[/bold]\n")
            u("INFO", "Launching AI workflow.")
            final_state = graph.invoke(initial_state)

            if isinstance(llm, GeminiLLMService):
                out.print(
                    f"[dim]Gemini cumulative tokens this run (reported): "
                    f"{llm.tokens_used_this_run}[/dim]"
                )

            phase = final_state.get("phase", "unknown")
            if phase == "deployed":
                out.print("\n[bold green]Done! PR has been created.[/bold green]")
                u("SUCCESS", "Completed successfully. Pull request created.")
                s("done")
            elif phase == "deployed_with_failed_tests":
                out.print(
                    "\n[bold yellow]Done! PR has been created, but the generated tests still failed.[/bold yellow]"
                )
                u("WARN", "PR created, but generated tests are still failing.")
                s("done")
            elif phase == "completed_local":
                out.print("\n[bold green]Done! Tests generated and saved locally (no PR).[/bold green]")
                u("SUCCESS", "Completed successfully. Tests saved locally.")
                s("done")
            elif phase == "completed_local_with_failed_tests":
                out.print(
                    "\n[bold yellow]Done! Tests were saved locally, but they still failed after retries.[/bold yellow]"
                )
                u("WARN", "Tests saved locally, but they are still failing.")
                s("done")
            elif phase == "cancelled":
                out.print("\n[yellow]Run cancelled by user.[/yellow]")
                u("WARN", "Run cancelled by user.")
                s("done")
            elif phase == "failed":
                out.print("\n[bold red]Pipeline failed after max retries.[/bold red]")
                u("ERROR", "Pipeline failed after maximum retries.")
                s("done")
            else:
                out.print(f"\n[dim]Pipeline ended in phase: {phase}[/dim]")
                u("INFO", f"Pipeline ended in phase: {phase}.")
                s("done")
            return phase
        except Exception as exc:
            u("ERROR", _friendly_error(exc))
            s("error")
            raise


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
    execute_run(ticket_id=ticket_id, config=config, console=console)


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
