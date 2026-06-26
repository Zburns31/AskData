from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

import pandas as pd
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from askdata.database import OrdersDatabase
from askdata.validator import SqlValidator

DEFAULT_GOOGLE_MODEL = "gemini-2.5-flash"


@dataclass(frozen=True)
class AgentTraceStep:
    name: str
    payload: str


@dataclass(frozen=True)
class QueryExecutionResult:
    question: str
    sql: str
    dataframe: pd.DataFrame
    trace: tuple[AgentTraceStep, ...]


class DataEngineerAgentError(RuntimeError):
    pass


class DataEngineerAgent:
    def __init__(
        self,
        database: OrdersDatabase | None = None,
        validator: SqlValidator | None = None,
        llm: Any | None = None,
        model: str | None = None,
    ) -> None:
        self.database = database or OrdersDatabase()
        self.validator = validator or SqlValidator(self.database)
        self.llm = llm or self._build_default_llm(model)

    def run(self, question: str) -> QueryExecutionResult:
        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("Question must not be empty.")

        trace: list[AgentTraceStep] = []
        schema_summary = self.database.get_schema_summary()
        trace.append(AgentTraceStep(name="get_schema_summary", payload=schema_summary))
        sql_candidate = self._generate_sql(normalized_question, schema_summary)
        trace.append(AgentTraceStep(name="generate_sql", payload=sql_candidate))
        validated_query = self.validator.validate(sql_candidate)
        trace.append(AgentTraceStep(name="validate_sql", payload=validated_query.sql))
        dataframe = self.database.execute_query(validated_query.sql)
        trace.append(AgentTraceStep(name="execute_query", payload=validated_query.sql))

        return QueryExecutionResult(
            question=normalized_question,
            sql=validated_query.sql,
            dataframe=dataframe,
            trace=tuple(trace),
        )

    def _build_default_llm(self, model: str | None) -> ChatGoogleGenerativeAI:
        if not os.getenv("GOOGLE_API_KEY"):
            raise DataEngineerAgentError(
                "GOOGLE_API_KEY is not set. Export it before running askdata."
            )
        return ChatGoogleGenerativeAI(
            model=model or os.getenv("ASKDATA_GOOGLE_MODEL", DEFAULT_GOOGLE_MODEL),
            temperature=0,
        )

    def _generate_sql(self, question: str, schema_summary: str) -> str:
        messages = [
            SystemMessage(
                content=(
                    "You translate analytics questions into a single SQLite query. "
                    "Return SQL only. Do not use markdown fences. "
                    "Use only SELECT or WITH queries. Never modify data. "
                    "Prefer explicit column names over SELECT *. "
                    "If the question cannot be answered from the schema, return "
                    "CANNOT_ANSWER. "
                    "Schema:\n"
                    f"{schema_summary}"
                )
            ),
            HumanMessage(content=question),
        ]
        response = self.llm.invoke(messages)
        content = self._response_to_text(response)
        sql = self._extract_sql(content)
        if sql == "CANNOT_ANSWER":
            raise DataEngineerAgentError(
                "The model could not answer the question from the available schema."
            )
        return sql

    def _response_to_text(self, response: Any) -> str:
        content = getattr(response, "content", response)
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and "text" in item:
                    parts.append(str(item["text"]))
            return "\n".join(parts).strip()
        return str(content).strip()

    def _extract_sql(self, content: str) -> str:
        if content.strip() == "CANNOT_ANSWER":
            return "CANNOT_ANSWER"

        fenced_match = re.search(
            r"```(?:sql)?\s*(.*?)```", content, re.IGNORECASE | re.DOTALL
        )
        if fenced_match:
            content = fenced_match.group(1).strip()

        sql_match = re.search(r"\b(select|with)\b[\s\S]*", content, re.IGNORECASE)
        if sql_match:
            return sql_match.group(0).strip().rstrip(";")

        raise DataEngineerAgentError("The model response did not contain a SQL query.")
