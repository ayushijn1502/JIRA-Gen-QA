from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ConversationTurn(BaseModel):
    role: MessageRole
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FindingSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    BLOCKER = "blocker"


class QAFinding(BaseModel):
    """One actionable insight surfaced during the conversation."""

    title: str
    detail: str
    severity: FindingSeverity = FindingSeverity.INFO
    related_ac: str | None = Field(default=None, description="Acceptance criterion reference, if any")


class QASession(BaseModel):
    ticket_id: str
    turns: list[ConversationTurn] = Field(default_factory=list)
    findings: list[QAFinding] = Field(default_factory=list)


class QASummary(BaseModel):
    """Exported artifact — input for a future pipeline hook."""

    ticket_id: str
    findings: list[QAFinding]
    open_questions: list[str] = Field(default_factory=list)
    suggested_scenarios: list[str] = Field(default_factory=list)
    transcript_turn_count: int
