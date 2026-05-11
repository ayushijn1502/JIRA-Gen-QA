"""
Prompt Builder -- reads the docs/*.md files and assembles system prompts
for each node in the LangGraph workflow.

Think of it as a "briefing packet" assembler: before each agent starts
its job, we hand it a packet that says "here's who you are, here are the
rules, and here's the context you need."  The content comes from the
markdown files the team maintains in /docs.

Usage:
    builder = PromptBuilder(docs_path="./docs")
    system_prompt = builder.build_analyze_prompt()
"""

from __future__ import annotations

from pathlib import Path


class PromptBuilder:
    """
    Reads markdown files from the docs/ directory once, then builds
    specialised system prompts for each workflow node on demand.
    """

    def __init__(self, docs_path: str = "./docs") -> None:
        self._docs_path = Path(docs_path)
        self._agents_md = self._read("agents.md")
        self._skills_md = self._read("skills.md")
        self._knowledge_base_md = self._read("knowledge_base.md")

    def _read(self, filename: str) -> str:
        """Read a single markdown file; return empty string if missing."""
        path = self._docs_path / filename
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def build_analyze_prompt(self) -> str:
        """
        System prompt for the Analyze node.
        Combines the JiraAnalyzer + FrameworkExpert personas with
        the skills catalogue so the LLM knows what tools it has.
        """
        return (
            "You are a senior QA analyst. Your job is to read a JIRA ticket "
            "and produce a detailed test plan.\n\n"
            "# Agent Roles\n" + self._agents_md + "\n\n"
            "# Available Skills\n" + self._skills_md + "\n\n"
            "# Rules\n" + self._knowledge_base_md
        )

    def build_generate_prompt(self) -> str:
        """
        System prompt for the Generate node.
        Gives the TestArchitect persona full access to the coding rules
        so it writes tests that match the project's style.
        """
        return (
            "You are a senior test automation engineer. Your job is to write "
            "clean, passing pytest code that follows every rule below.\n\n"
            "# Coding Standards & Rules\n" + self._knowledge_base_md + "\n\n"
            "# Agent Roles\n" + self._agents_md
        )

    def build_fix_prompt(self) -> str:
        """
        System prompt used when tests failed and we need the LLM
        to fix its own code.  Emphasises the error output and the
        coding rules it probably violated.
        """
        return (
            "You are a senior test automation engineer debugging a test failure. "
            "The previous code you generated failed pytest. "
            "Fix the code so all tests pass. "
            "Pay close attention to the error output and the coding rules.\n\n"
            "# Coding Standards & Rules\n" + self._knowledge_base_md
        )

    def build_test_matrix_prompt(self) -> str:
        """System prompt for the matrix_csv node — test case CSV before codegen."""
        matrix_rules = self._read("test_matrix.md")
        hard_constraints = (
            "\n\n# Hard constraints (do not violate)\n"
            "- Every row: all five fields are non-empty strings; use `N/A` only as allowed in the rules.\n"
            "- `testcase`: unique short title per row; include the JIRA key from the user message when possible.\n"
            "- `test_steps`: always numbered lines (1. 2. …), newline-separated.\n"
            "- Output must be a single JSON object with key `rows` only; no markdown fences.\n"
        )
        return (
            "You are a senior QA analyst. Expand the JIRA ticket and test plan into "
            "a formal test-case matrix (rows for a spreadsheet).\n\n"
            + (matrix_rules if matrix_rules else "# Rules\nProduce detailed matrix rows.\n")
            + hard_constraints
            + "\n\n# Agent Roles\n"
            + self._agents_md
        )

