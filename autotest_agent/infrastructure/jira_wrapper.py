"""
JIRA Wrapper -- talks to JIRA and converts raw ticket data into our
clean JiraTicket model.

Think of it as a translator: JIRA speaks its own language (with custom
fields, rich-text descriptions, etc.), and this class converts that into
the simple format the rest of our system understands.

Usage:
    wrapper = JiraWrapper(url="https://org.atlassian.net",
                          email="me@co.com", api_token="tok")
    ticket = wrapper.fetch_ticket("PROJ-42")
    print(ticket.acceptance_criteria)
"""

from __future__ import annotations

import re

from jira import JIRA

from autotest_agent.domain.models import JiraTicket
from autotest_agent.domain.ports import JiraPort


class JiraWrapper(JiraPort):
    """
    Concrete implementation of JiraPort.
    Uses the `python-jira` library under the hood to call the JIRA REST API,
    then extracts the fields we care about into a JiraTicket.
    """

    def __init__(self, url: str, email: str, api_token: str) -> None:
        self._client = JIRA(server=url, basic_auth=(email, api_token))

    def fetch_ticket(self, ticket_id: str) -> JiraTicket:
        """
        Pull a single ticket from JIRA by its key (e.g. PROJ-123)
        and return a structured JiraTicket with the important bits.
        """
        issue = self._client.issue(ticket_id)
        description = issue.fields.description or ""
        return JiraTicket(
            id=issue.key,
            title=issue.fields.summary,
            description=description,
            acceptance_criteria=self._extract_acceptance_criteria(description),
        )

    @staticmethod
    def _extract_acceptance_criteria(description: str) -> list[str]:
        """
        Try to pull acceptance criteria out of the description text.
        Looks for a section headed "Acceptance Criteria" and grabs the
        bullet points underneath it.  If none found, returns an empty list.
        """
        pattern = r"(?i)acceptance\s+criteria[:\s]*\n((?:[\s]*[-*]\s*.+\n?)+)"
        match = re.search(pattern, description)
        if not match:
            return []
        raw_lines = match.group(1).strip().splitlines()
        return [re.sub(r"^[\s\-*]+", "", line).strip() for line in raw_lines if line.strip()]
