from __future__ import annotations

import json
from pathlib import Path

from autotest_agent.domain.models import JiraTicket
from autotest_agent.domain.ports import LLMPort, RAGPort
from conversation_qa.models import (
    ConversationTurn,
    MessageRole,
    QAFinding,
    QASession,
    QASummary,
)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "qa_analyst.md"
_OUTPUT_DIR = Path(__file__).parent / "output"


class ConversationQAAssistant:
    def __init__(self, llm: LLMPort, rag: RAGPort | None = None) -> None:
        self._llm = llm
        self._rag = rag
        self._system_prompt = _PROMPT_PATH.read_text(encoding="utf-8")
        self._session: QASession | None = None

    def start(self, ticket: JiraTicket, rag_query: str | None = None) -> str:
        context_chunks: list[str] = []
        if self._rag and rag_query:
            context_chunks = self._rag.query(rag_query, top_k=3)

        self._session = QASession(ticket_id=ticket.id)
        intro = self._build_ticket_context(ticket, context_chunks)
        self._session.turns.append(
            ConversationTurn(role=MessageRole.SYSTEM, content=self._system_prompt)
        )
        self._session.turns.append(
            ConversationTurn(role=MessageRole.ASSISTANT, content=intro)
        )
        return intro

    def ask(self, user_message: str) -> str:
        if not self._session:
            raise RuntimeError("Call start() before ask()")
        self._session.turns.append(
            ConversationTurn(role=MessageRole.USER, content=user_message)
        )
        reply = self._llm.chat(self._to_llm_messages())
        self._session.turns.append(
            ConversationTurn(role=MessageRole.ASSISTANT, content=reply)
        )
        return reply

    def export_summary(self) -> Path:
        if not self._session:
            raise RuntimeError("No active session")
        summary_prompt = (
            "Based on our conversation, respond with ONLY valid JSON matching this schema:\n"
            '{"findings":[{"title":"...","detail":"...","severity":"info|warning|blocker","related_ac":null}],'
            '"open_questions":["..."],"suggested_scenarios":["..."]}\n'
            "No markdown fences."
        )
        raw = self._llm.chat(self._to_llm_messages() + [("user", summary_prompt)])
        data = json.loads(raw)
        summary = QASummary(
            ticket_id=self._session.ticket_id,
            findings=[QAFinding(**f) for f in data.get("findings", [])],
            open_questions=data.get("open_questions", []),
            suggested_scenarios=data.get("suggested_scenarios", []),
            transcript_turn_count=len(self._session.turns),
        )
        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out = _OUTPUT_DIR / f"{self._session.ticket_id}_qa_findings.json"
        out.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
        return out

    def _to_llm_messages(self) -> list[tuple[str, str]]:
        assert self._session
        turns = self._session.turns
        if len(turns) > 10:
            turns = [turns[0], *turns[-9:]]
        return [(t.role.value, t.content) for t in turns]

    @staticmethod
    def _build_ticket_context(ticket: JiraTicket, rag_chunks: list[str]) -> str:
        ac = "\n".join(f"  {i+1}. {c}" for i, c in enumerate(ticket.acceptance_criteria))
        rag = "\n\n".join(rag_chunks) if rag_chunks else "(no code context retrieved)"
        return (
            f"**Ticket {ticket.id}:** {ticket.title}\n\n"
            f"**Description:**\n{ticket.description}\n\n"
            f"**Acceptance criteria:**\n{ac or '  (none parsed)'}\n\n"
            f"**Relevant code (RAG):**\n{rag}\n\n"
            "Ask me anything about testability, coverage, or ambiguities."
        )
