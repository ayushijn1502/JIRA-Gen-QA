"""
GitHub Service -- creates branches, commits files, and opens pull requests
using the PyGithub library.

Think of it as a "robot git assistant": you tell it which files changed
and what the PR should say, and it handles all the GitHub API calls.

Usage:
    svc = GitHubService(token="ghp_...", repo="owner/repo")
    svc.create_branch("autotest/PROJ-42")
    svc.commit_and_push(
        files={"tests/test_new.py": "<code>"},
        message="test: add tests for PROJ-42",
        branch_name="autotest/PROJ-42",
    )
    pr_url = svc.create_pr("Add tests for PROJ-42", "...", "autotest/PROJ-42")
"""

from __future__ import annotations

from github import Github

from autotest_agent.domain.ports import GitPort


class GitHubService(GitPort):
    """
    Concrete implementation of GitPort.
    Uses PyGithub to interact with the GitHub REST API.
    All operations go through a personal access token.
    """

    def __init__(self, token: str, repo: str, base_branch: str = "main") -> None:
        self._github = Github(token)
        self._repo = self._github.get_repo(repo)
        self._base_branch = base_branch

    def create_branch(self, branch_name: str) -> None:
        """
        Create a new branch off the base branch (usually 'main').
        If the branch already exists, this is a no-op.
        """
        base_ref = self._repo.get_git_ref(f"heads/{self._base_branch}")
        base_sha = base_ref.object.sha
        try:
            self._repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=base_sha)
        except Exception:
            pass  # Branch already exists

    def commit_and_push(self, files: dict[str, str], message: str, branch_name: str) -> None:
        """
        Create or update files on the given branch in a single commit.
        `files` is a dict of {file_path: file_content}.
        """
        for file_path, content in files.items():
            try:
                existing = self._repo.get_contents(file_path, ref=branch_name)
                self._repo.update_file(
                    path=file_path,
                    message=message,
                    content=content,
                    sha=existing.sha,
                    branch=branch_name,
                )
            except Exception:
                self._repo.create_file(
                    path=file_path,
                    message=message,
                    content=content,
                    branch=branch_name,
                )

    def create_pr(self, title: str, body: str, branch_name: str) -> str:
        """
        Open a pull request from `branch_name` into the base branch.
        Returns the URL of the newly created PR.
        """
        pr = self._repo.create_pull(
            title=title,
            body=body,
            head=branch_name,
            base=self._base_branch,
        )
        return pr.html_url


class SkippedGitHubService(GitPort):
    """
    Stand-in when GitHub is turned off in config.

    Does not talk to the network.  The workflow still finishes after
    pytest passes; the generated file is only on your machine.
    """

    def create_branch(self, branch_name: str) -> None:
        """No-op: we are not creating a remote branch."""

    def commit_and_push(self, files: dict[str, str], message: str, branch_name: str) -> None:
        """No-op: we are not pushing to GitHub."""

    def create_pr(self, title: str, body: str, branch_name: str) -> str:
        """Return a placeholder message instead of a real PR URL."""
        return "(GitHub disabled — no pull request created)"
