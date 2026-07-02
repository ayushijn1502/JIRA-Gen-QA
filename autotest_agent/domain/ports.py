"""
Ports -- abstract interfaces that define *what* the system needs
without saying *how* it's done.

In Hexagonal Architecture these are the "plugs" on the domain boundary.
The domain layer says "I need something that can fetch a JIRA ticket"
but doesn't care whether it uses the python-jira library, a REST call,
or a local JSON file.  The concrete implementation lives in
`infrastructure/` and gets wired in at startup.

Why bother?  Because it makes testing trivial -- swap in a fake
implementation and the whole workflow runs without touching JIRA / GitHub
/ the network at all.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TypeVar

from autotest_agent.domain.models import (
    JiraTicket,
    VerificationResult,
)

T = TypeVar("T")


class JiraPort(ABC):
    """Anything that can fetch and parse a JIRA ticket."""

    @abstractmethod
    def fetch_ticket(self, ticket_id: str) -> JiraTicket:
        """
        Go to JIRA, grab the ticket with this ID, and return it
        as a nice JiraTicket object.
        """


class RAGPort(ABC):
    """Anything that can index code files and answer questions about them."""

    @abstractmethod
    def index_codebase(self, path: str) -> None:
        """
        Walk a directory of Python files, chop them into chunks,
        generate embeddings, and store them so we can search later.
        """

    @abstractmethod
    def query(self, question: str, top_k: int = 5) -> list[str]:
        """
        Given a natural-language question, return the top_k most
        relevant code chunks from the index.
        """


class LLMPort(ABC):
    """Anything that can call a large language model and get structured output."""

    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[Any] | None = None,
    ) -> Any:
        """
        Send a system prompt + user prompt to the LLM.
        If output_schema is provided, parse the response into that
        Pydantic model.  Otherwise return raw text.
        """

    @abstractmethod
    def chat(self, messages: list[tuple[str, str]]) -> str:
        """Multi-turn chat. Each item is (role, content) where role is 'system'|'user'|'assistant'."""


class GitPort(ABC):
    """Anything that can push code to GitHub and open a pull request."""

    @abstractmethod
    def create_branch(self, branch_name: str) -> None:
        """Create a new git branch from the default base branch."""

    @abstractmethod
    def commit_and_push(self, files: dict[str, str], message: str, branch_name: str) -> None:
        """
        Commit one or more files (path -> content) to the given branch
        and push to the remote.
        """

    @abstractmethod
    def create_pr(self, title: str, body: str, branch_name: str) -> str:
        """
        Open a pull request from branch_name into the base branch.
        Return the URL of the new PR.
        """


class TestRunnerPort(ABC):
    """Anything that can execute pytest on a file and report results."""

    @abstractmethod
    def run_tests(self, test_file_path: str) -> VerificationResult:
        """
        Run pytest against the given file and return whether it
        passed, along with any output or error logs.
        """
