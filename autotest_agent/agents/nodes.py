"""
Graph Nodes -- the four "workers" that sit inside the LangGraph state machine.

Each function receives the current GraphState (a shared dict), does its job,
and returns a partial dict with only the keys it updated.  LangGraph merges
those updates back into the state automatically.

Analogy: imagine a factory assembly line where each station reads the
work-order clipboard, does one thing, writes its result on the clipboard,
and passes it along.

Usage:
    These functions are not called directly -- they're registered as
    nodes in the StateGraph (see graph.py).
"""

from __future__ import annotations

from pathlib import Path
import csv
from collections.abc import Callable
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from autotest_agent.agents.prompts import PromptBuilder
from autotest_agent.config import PocSettings
from autotest_agent.domain.models import GeneratedTest, GraphState, TestMatrixDocument, TestPlan
from autotest_agent.domain.ports import GitPort, LLMPort, RAGPort, TestRunnerPort
from autotest_agent.infrastructure.output_paths import (
    resolve_generated_test_path,
    resolve_matrix_csv_path,
)

def _build_failure_summary(output: str, error_log: str, limit: int = 1500) -> str:
    combined = "\n".join(part for part in [output.strip(), error_log.strip()] if part).strip()
    if not combined:
        return "Pytest failed, but no output was captured."
    if len(combined) <= limit:
        return combined
    return combined[:limit].rstrip() + "\n... [truncated]"


class NodeContainer:
    """
    Holds references to all the infrastructure services (ports) that
    the nodes need.  This is our simple dependency-injection mechanism --
    build it once at startup, then pass it to each node.

    Why a container?  LangGraph node functions must have the signature
    `(state) -> dict`, so we can't inject dependencies through the function
    signature.  Instead each node is a *method* on this container, which
    already has access to the services via `self`.
    """

    def __init__(
        self,
        llm: LLMPort,
        rag: RAGPort,
        git: GitPort,
        test_runner: TestRunnerPort,
        prompt_builder: PromptBuilder,
        target_framework_path: str,
        skip_github: bool = False,
        poc: PocSettings | None = None,
        console: Console | None = None,
        text_input: Callable[[str], str] | None = None,
        user_log: Callable[[str, str], None] | None = None,
        on_stage: Callable[[str], None] | None = None,
        on_matrix_csv: Callable[[str], None] | None = None,
    ) -> None:
        self.llm = llm
        self.rag = rag
        self.git = git
        self.test_runner = test_runner
        self.prompts = prompt_builder
        self.target_framework_path = target_framework_path
        self.skip_github = skip_github
        self._poc = poc or PocSettings(enabled=False)
        self.console = console or Console()
        self._text_input = text_input or self.console.input
        self._user_log = user_log
        self._on_stage = on_stage
        self._on_matrix_csv = on_matrix_csv

    def _u(self, level: str, msg: str) -> None:
        if self._user_log is not None:
            self._user_log(level, msg)

    def _stage(self, stage_id: str) -> None:
        if self._on_stage is not None:
            self._on_stage(stage_id)

    def _rag_chunks_analyze(self) -> int:
        return self._poc.analyze_rag_chunks if self._poc.enabled else 5

    def _rag_chunks_generate(self) -> int:
        return self._poc.generate_rag_chunks if self._poc.enabled else 5

    # ------------------------------------------------------------------
    # Node 1: Analyze
    # ------------------------------------------------------------------

    def analyze(self, state: GraphState) -> dict[str, Any]:
        """
        Read the JIRA ticket that's already in the state, query RAG for
        related code, and produce a TestPlan describing what tests to write.

        After this node the state will have a `plan` key.
        """
        self._stage("analyze")
        ticket = state["ticket"]
        self.console.print(f"\n[bold blue]Analyzing ticket {ticket.id}...[/bold blue]")
        self._u("INFO", "Analyzing ticket requirements and existing code context.")

        query_text = f"{ticket.title}\n{ticket.description}"
        relevant_chunks = self.rag.query(query_text)
        n_analyze = self._rag_chunks_analyze()
        n_keep = (
            max(self._poc.analyze_rag_chunks, self._poc.generate_rag_chunks)
            if self._poc.enabled
            else len(relevant_chunks)
        )
        chunks_for_prompt = relevant_chunks[:n_analyze]
        chunks_stored = relevant_chunks[:n_keep] if self._poc.enabled else relevant_chunks

        system_prompt = self.prompts.build_analyze_prompt()
        user_prompt = (
            f"JIRA Ticket: {ticket.id}\n"
            f"Title: {ticket.title}\n"
            f"Description:\n{ticket.description}\n\n"
            f"Acceptance Criteria:\n"
            + "\n".join(f"- {ac}" for ac in ticket.acceptance_criteria)
            + "\n\nExisting code context:\n"
            + "\n---\n".join(chunks_for_prompt)
            + "\n\nIMPORTANT: New tests MUST live under the target_framework tests folder only. "
            "Set target_file to a path relative to target_framework, like "
            "`tests/test_something.py` (never src/ or repo root).\n\n"
            "Your entire answer must be ONE JSON object only: start with { and end with }. "
            "No introduction, no markdown, no text before or after the JSON.\n\n"
            "Produce a TestPlan with: ticket_id, target_file, test_scenarios, "
            "and relevant_context."
        )
        if self._poc.max_test_scenarios == 2:
            user_prompt += (
                "\n\nLIMIT: test_scenarios must contain exactly two strings, in order: "
                "(1) one positive / happy-path case; (2) one negative case "
                "(invalid input, error path, or expected failure). "
                "One short line each. No other scenarios."
            )

        plan: TestPlan = self.llm.generate(system_prompt, user_prompt, TestPlan)
        plan.relevant_context = chunks_stored
        forced = resolve_generated_test_path(
            plan.target_file,
            ticket.id,
            self.target_framework_path,
        )
        plan = plan.model_copy(
            update={
                "ticket_id": ticket.id,
                "target_file": f"tests/{Path(forced).name}",
            }
        )
        cap = self._poc.max_test_scenarios
        plan = plan.model_copy(update={"test_scenarios": plan.test_scenarios[:cap]})

        self.console.print(f"[green]Test plan created with {len(plan.test_scenarios)} scenarios[/green]")
        for i, scenario in enumerate(plan.test_scenarios, 1):
            self.console.print(f"  {i}. {scenario}")
        self._u("SUCCESS", f"Created test plan with {len(plan.test_scenarios)} scenarios.")

        return {"plan": plan, "phase": "analyze_complete"}

    def matrix_csv(self, state: GraphState) -> dict[str, Any]:
        self._stage("matrix_csv")
        ticket = state["ticket"]
        plan = state["plan"]
        out_path = Path(resolve_matrix_csv_path(ticket.id, self.target_framework_path))
        matrix_doc: TestMatrixDocument | None = None
        try:
            system_prompt = self.prompts.build_matrix_csv_prompt()
            user_prompt = (
                f"Ticket: {ticket.id}\n"
                f"Title: {ticket.title}\n"
                f"Description: {ticket.description}\n\n"
                "Acceptance Criteria:\n"
                + "\n".join(f"- {ac}" for ac in ticket.acceptance_criteria)
                + "\n\nPlanned scenarios:\n"
                + "\n".join(f"- {scenario}" for scenario in plan.test_scenarios)
                + "\n\nReturn JSON only."
            )
            matrix_doc = self.llm.generate(system_prompt, user_prompt, TestMatrixDocument)
        except Exception as exc:
            self.console.print(
                f"[yellow]Matrix generation fallback enabled due to model parsing error: {exc}[/yellow]"
            )
            self._u(
                "WARN",
                "Could not parse structured matrix output from model. Using scenario-based fallback rows.",
            )
        if matrix_doc is None or not matrix_doc.rows:
            fallback_rows = [
                {
                    "testcase": f"TC-{i:02d}",
                    "description": scenario,
                    "pre_condition": "Application is reachable and test data is prepared.",
                    "test_steps": scenario,
                    "expected_results": "System behavior matches the scenario expectation.",
                }
                for i, scenario in enumerate(plan.test_scenarios, start=1)
            ]
            matrix_doc = TestMatrixDocument.model_validate({"rows": fallback_rows})
        with out_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                ["testcase", "Description", "PreCondition", "TestSteps", "Expected Results"]
            )
            for row in matrix_doc.rows:
                writer.writerow(
                    [
                        row.testcase,
                        row.description,
                        row.pre_condition,
                        row.test_steps,
                        row.expected_results,
                    ]
                )
        self.console.print(f"[green]Test matrix CSV saved: {out_path}[/green]")
        self._u("SUCCESS", f"Test matrix saved: {out_path}")
        if self._on_matrix_csv is not None:
            self._on_matrix_csv(str(out_path))
        return {"test_matrix_csv_path": str(out_path)}

    # ------------------------------------------------------------------
    # Node 2: Generate
    # ------------------------------------------------------------------

    def generate(self, state: GraphState) -> dict[str, Any]:
        """
        Take the TestPlan and ask the LLM to write actual pytest code.
        If this is a retry (tests failed before), include the error logs
        so the LLM can fix its own mistakes.

        After this node the state will have a `generated_test` key.
        """
        self._stage("generate")
        plan = state["plan"]
        retry_count = state.get("retry_count", 0)
        error_history = state.get("error_history", [])

        if retry_count > 0:
            self.console.print(
                f"\n[bold yellow]Retry {retry_count}: regenerating code...[/bold yellow]"
            )
            system_prompt = self.prompts.build_fix_prompt()
            self._u("WARN", f"Fixing test code based on previous pytest errors (retry {retry_count}).")
        else:
            self.console.print("\n[bold blue]Generating test code...[/bold blue]")
            self._u("INFO", "Generating automation tests from the plan.")
            system_prompt = self.prompts.build_generate_prompt()

        n_gen = self._rag_chunks_generate()
        user_prompt = (
            f"Ticket: {plan.ticket_id}\n"
            f"Target file: {plan.target_file}\n\n"
            f"Test scenarios:\n"
            + "\n".join(f"- {s}" for s in plan.test_scenarios)
            + "\n\nRelevant existing code:\n"
            + "\n---\n".join(plan.relevant_context[:n_gen])
        )
        matrix_path = state.get("test_matrix_csv_path")
        if matrix_path:
            user_prompt += f"\n\nMatrix CSV path: {matrix_path}"

        if error_history:
            user_prompt += (
                "\n\nPrevious attempt failed with these errors:\n"
                + "\n".join(error_history[-2:])
            )

        user_prompt += (
            "\n\nGenerate a complete pytest file. "
            "Return JSON with: file_path, code, explanation. "
            "file_path MUST be relative to the repo root and MUST start with "
            "`target_framework/tests/` (only that folder). "
            "Your entire answer must be ONE JSON object only: start with { and end with }."
        )
        if self._poc.max_test_scenarios == 2 or self._poc.enabled:
            user_prompt += (
                "\n\nLIMIT: Implement only the listed scenarios—typically two tests "
                "(one positive, one negative). Keep the file small: minimal imports, "
                "no parametrized matrices, no extra edge cases or docstring essays."
            )

        result: GeneratedTest = self.llm.generate(system_prompt, user_prompt, GeneratedTest)
        forced_path = resolve_generated_test_path(
            result.file_path,
            state["ticket"].id,
            self.target_framework_path,
        )
        result = result.model_copy(update={"file_path": forced_path})
        self.console.print(f"[green]Generated test file: {result.file_path}[/green]")
        self._u("SUCCESS", f"Generated test file at {result.file_path}.")

        return {"generated_test": result, "phase": "generate_complete"}

    # ------------------------------------------------------------------
    # Node 3: Verify
    # ------------------------------------------------------------------

    def verify(self, state: GraphState) -> dict[str, Any]:
        """
        Write the generated code to disk, run pytest, and record the result.
        If the tests fail, bump the retry counter and save the error log
        so the next Generate pass can see what went wrong.

        After this node the state will have `verification` and updated
        `retry_count` / `error_history`.
        """
        self._stage("verify")
        generated = state["generated_test"]
        retry_count = state.get("retry_count", 0)
        error_history = list(state.get("error_history", []))

        self.console.print(f"\n[bold blue]Writing test to {generated.file_path}...[/bold blue]")
        test_path = Path(generated.file_path)
        test_path.parent.mkdir(parents=True, exist_ok=True)
        test_path.write_text(generated.code, encoding="utf-8")

        self.console.print("[bold blue]Running pytest...[/bold blue]")
        self._u("INFO", "Running pytest to verify generated tests.")
        verification = self.test_runner.run_tests(str(test_path))

        if verification.passed:
            self.console.print("[bold green]All tests passed![/bold green]")
            self._u("SUCCESS", "Generated tests passed.")
        else:
            self.console.print("[bold red]Tests failed.[/bold red]")
            self.console.print(verification.output[:2000])
            error_history.append(verification.output + "\n" + verification.error_log)
            retry_count += 1
            self._u("WARN", "Generated tests failed. Retrying with failure feedback.")

        return {
            "verification": verification,
            "retry_count": retry_count,
            "error_history": error_history,
            "phase": "verify_complete",
        }

    # ------------------------------------------------------------------
    # Node 4: Deploy
    # ------------------------------------------------------------------

    def deploy(self, state: GraphState) -> dict[str, Any]:
        """
        Show the generated code to the user for approval (the "approval
        gate"), then push it to GitHub and open a pull request.

        This is the last node -- after it runs the workflow is done.
        """
        self._stage("deploy")
        generated = state["generated_test"]
        ticket = state["ticket"]
        verification = state.get("verification")
        tests_failed = bool(verification and not verification.passed)
        failure_summary = ""
        if tests_failed:
            failure_summary = _build_failure_summary(
                verification.output,
                verification.error_log,
            )

        self.console.print("\n[bold]Generated test code for your review:[/bold]")
        self.console.print(Panel(
            Syntax(generated.code, "python", theme="monokai", line_numbers=True),
            title=generated.file_path,
        ))
        self.console.print(f"\n[dim]{generated.explanation}[/dim]\n")
        self._u("INFO", "Awaiting your approval to finish deployment.")
        if tests_failed:
            self.console.print(
                "[bold yellow]Generated tests still failed after all retries. "
                "You can still create a PR with the failing output.[/bold yellow]"
            )
            self.console.print(Panel(failure_summary, title="Latest pytest failure", border_style="yellow"))
            self._u("WARN", "Tests still failing after retries. You can still approve deployment.")

        if self.skip_github and tests_failed:
            prompt = (
                "[bold yellow]Approve and finish even though tests failed? "
                "(GitHub off — no PR; file is already saved on disk) (y/N): [/bold yellow]"
            )
        elif self.skip_github:
            prompt = (
                "[bold yellow]Approve and finish? "
                "(GitHub off — no PR; file is already saved on disk) (y/N): [/bold yellow]"
            )
        elif tests_failed:
            prompt = (
                "[bold yellow]Approve and create PR even though generated tests failed? "
                "(y/N): [/bold yellow]"
            )
        else:
            prompt = "[bold yellow]Approve and create PR? (y/N): [/bold yellow]"

        approved = self._text_input(prompt)
        if approved.strip().lower() != "y":
            self.console.print("[red]Cancelled by user.[/red]")
            self._u("WARN", "Deployment cancelled by user.")
            return {"phase": "cancelled"}

        if self.skip_github:
            self.console.print(
                "\n[bold green]Done. Test file is on disk; GitHub step was skipped.[/bold green]"
            )
            self._u("SUCCESS", "Completed locally. GitHub was skipped.")
            return {
                "phase": "completed_local_with_failed_tests" if tests_failed else "completed_local"
            }

        branch_name = f"autotest/{ticket.id}"
        self.console.print(f"[blue]Creating branch {branch_name}...[/blue]")
        self._u("INFO", "Creating GitHub branch and opening pull request.")
        self.git.create_branch(branch_name)

        commit_msg = f"test: add tests for {ticket.id} - {ticket.title}"
        self.git.commit_and_push(
            files={generated.file_path: generated.code},
            message=commit_msg,
            branch_name=branch_name,
        )

        pr_body = (
            f"## Auto-generated tests for {ticket.id}\n\n"
            f"**Ticket:** {ticket.title}\n\n"
            f"**Scenarios covered:**\n"
            + "\n".join(f"- {s}" for s in state["plan"].test_scenarios)
            + f"\n\n**Explanation:** {generated.explanation}"
        )
        if tests_failed:
            pr_body += (
                "\n\n**Verification status:** Tests failed after all retries.\n\n"
                "```text\n"
                f"{failure_summary}\n"
                "```"
            )
        pr_url = self.git.create_pr(
            title=f"test: {ticket.id} - {ticket.title}",
            body=pr_body,
            branch_name=branch_name,
        )

        self.console.print(f"\n[bold green]PR created: {pr_url}[/bold green]")
        self._u("SUCCESS", f"Pull request created: {pr_url}")
        return {"phase": "deployed_with_failed_tests" if tests_failed else "deployed"}
