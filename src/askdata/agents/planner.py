from __future__ import annotations

import os
from dataclasses import dataclass

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from askdata.agents.config import AgentConfig
from askdata.observability import get_langfuse_callback, observe

__all__ = ["PlannerAgent", "PlannerAgentError"]

_SYSTEM_PROMPT = """\
You are a data analyst assistant that helps users ask precise, answerable questions
about a SQLite database. Given the database schema and a user question, your job is
to produce a single, clear, self-contained analytical question that a SQL query can
directly answer.

Rules:
- Return only the refined question as plain text. No preamble, no explanation.
- Preserve the user's intent. Do not change what they are asking.
- Make the question specific: clarify ambiguous terms (e.g. "recent" → a time range
  if implied, or note the lack of filter), name the relevant tables/concepts from
  the schema, and remove any part that cannot be answered from the schema.
- If the question is already precise and answerable, return it unchanged.
- Never answer the question yourself. Only refine it.
"""


@dataclass(frozen=True)
class PlannerResult:
    original_question: str
    refined_question: str


class PlannerAgentError(RuntimeError):
    pass


class PlannerAgent:
    """Refines a raw user question into a precise, schema-grounded analytical question."""

    def __init__(
        self,
        llm: object | None = None,
        config: AgentConfig | None = None,
    ) -> None:
        self.config = config or AgentConfig()
        self.llm = llm or self._build_default_llm()

    @observe(name="PlannerAgent.run")
    def run(self, question: str, schema_summary: str) -> PlannerResult:
        """Refine *question* using *schema_summary* as grounding context."""
        normalized = question.strip()
        if not normalized:
            raise PlannerAgentError("Question must not be empty.")

        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(
                content=(f"Schema:\n{schema_summary}\n\nUser question: {normalized}")
            ),
        ]

        callbacks = [cb for cb in [get_langfuse_callback()] if cb is not None]
        response = self.llm.invoke(messages, config={"callbacks": callbacks})

        raw = response.content
        refined = (
            "".join(p if isinstance(p, str) else p.get("text", "") for p in raw)
            if isinstance(raw, list)
            else raw
        ).strip()
        if not refined:
            raise PlannerAgentError("Planner returned an empty question.")

        return PlannerResult(
            original_question=normalized,
            refined_question=refined,
        )

    def _build_default_llm(self) -> ChatGoogleGenerativeAI:
        if not os.getenv("GOOGLE_API_KEY"):
            raise PlannerAgentError(
                "GOOGLE_API_KEY is not set. Export it before running askdata."
            )
        return ChatGoogleGenerativeAI(
            model=os.getenv("ASKDATA_GOOGLE_MODEL", self.config.model),
            temperature=self.config.temperature,
        )
