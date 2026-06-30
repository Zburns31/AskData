from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

import pandas as pd
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from askdata.agents.config import AgentConfig
from askdata.observability import get_langfuse_callback, observe, trace
from askdata.sql.validator import SqlValidator
from askdata.storage.database import SQLiteDatabase

MAX_SQL_RETRIES = 2

# (question, sql) pairs injected before the real question to demonstrate JOIN and CTE patterns.
FEW_SHOT_EXAMPLES: tuple[tuple[str, str], ...] = (
    (
        "How many orders does each seller have? Show the top 10 sellers by order count.",
        """
        SELECT s.seller_id, s.seller_city, s.seller_state, COUNT(oi.order_id) AS order_count
            FROM sellers s
            JOIN order_items oi ON s.seller_id = oi.seller_id
            GROUP BY s.seller_id, s.seller_city, s.seller_state
            ORDER BY order_count DESC
            LIMIT 10
        """,
    ),
    (
        "What is the top product category by total revenue? Include the product category and number of units",
        """WITH category_sales AS (
            SELECT p."product category" AS product_category, SUM(oi.price) AS total_sales
            FROM order_items AS oi
            INNER JOIN products AS p ON oi.product_id = p.product_id
            WHERE p."product category" IS NOT NULL
            GROUP BY p."product category"
        ),
        top_category AS (
            SELECT product_category, total_sales
            FROM category_sales
            ORDER BY total_sales DESC
            LIMIT 1
        )
        SELECT tc.product_category,
            strftime('%Y-%m', o.order_purchase_timestamp) AS sales_month,
            COUNT(DISTINCT oi.order_id) AS num_orders,
            SUM(oi.price) AS monthly_sales
        FROM order_items AS oi
        INNER JOIN products AS p ON oi.product_id = p.product_id
        INNER JOIN orders AS o ON oi.order_id = o.order_id
        INNER JOIN top_category AS tc ON p."product category" = tc.product_category
        WHERE o.order_purchase_timestamp IS NOT NULL
        GROUP BY tc.product_category, strftime('%Y-%m', o.order_purchase_timestamp)
        ORDER BY sales_month ASC
        """,
    ),
)


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
    def __init__(
        self,
        message: str,
        *,
        sql: str | None = None,
        trace: tuple[AgentTraceStep, ...] = (),
    ) -> None:
        """Capture the attempted SQL and trace context for eval reporting."""
        super().__init__(message)
        self.sql = sql
        self.trace = trace


class DataEngineerAgent:
    def __init__(
        self,
        database: SQLiteDatabase | None = None,
        validator: SqlValidator | None = None,
        llm: Any | None = None,
        config: AgentConfig | None = None,
    ) -> None:
        """Wire together the database, validator, and LLM used for question answering."""
        self.config = config or AgentConfig()
        self.database = database or SQLiteDatabase()
        self.validator = validator or SqlValidator(self.database)
        self.llm = llm or self._build_default_llm()

    @trace(name="DataEngineerAgent.run")
    def run(self, question: str) -> QueryExecutionResult:
        """Translate a natural-language question into SQL, validate it, and run it."""
        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("Question must not be empty.")

        trace: list[AgentTraceStep] = []
        trace.append(
            AgentTraceStep(name="thinking_level", payload=self.config.thinking_level)
        )
        schema_summary = self.database.get_schema_summary()
        trace.append(AgentTraceStep(name="get_schema_summary", payload=schema_summary))

        prior_error: str | None = None
        last_sql: str | None = None
        validated_query = None
        for attempt in range(MAX_SQL_RETRIES + 1):
            try:
                sql_candidate, thinking_tokens = self._generate_sql(
                    normalized_question, schema_summary, prior_error=prior_error
                )
            except Exception as error:
                trace.append(
                    AgentTraceStep(name="generate_sql_error", payload=str(error))
                )
                raise DataEngineerAgentError(
                    f"SQL generation failed: {error}",
                    trace=tuple(trace),
                ) from error
            if self.config.debug and thinking_tokens:
                trace.append(
                    AgentTraceStep(name="thinking_tokens", payload=thinking_tokens)
                )
            trace.append(AgentTraceStep(name="generate_sql", payload=sql_candidate))
            last_sql = sql_candidate
            try:
                validated_query = self.validator.validate(sql_candidate)
                break  # validation passed — exit retry loop
            except Exception as error:
                trace.append(
                    AgentTraceStep(name="validate_sql_error", payload=str(error))
                )
                prior_error = str(error)
                if attempt == MAX_SQL_RETRIES:
                    raise DataEngineerAgentError(
                        f"Generated SQL failed validation after {MAX_SQL_RETRIES + 1}"
                        f" attempts: {error}",
                        sql=last_sql,
                        trace=tuple(trace),
                    ) from error

        assert validated_query is not None
        trace.append(AgentTraceStep(name="validate_sql", payload=validated_query.sql))
        try:
            dataframe = self.database.execute_query(validated_query.sql)
        except Exception as error:
            trace.append(AgentTraceStep(name="execute_query_error", payload=str(error)))
            raise DataEngineerAgentError(
                f"Validated SQL failed during execution: {error}",
                sql=validated_query.sql,
                trace=tuple(trace),
            ) from error
        trace.append(AgentTraceStep(name="execute_query", payload=validated_query.sql))

        return QueryExecutionResult(
            question=normalized_question,
            sql=validated_query.sql,
            dataframe=dataframe,
            trace=tuple(trace),
        )

    def _build_default_llm(self) -> ChatGoogleGenerativeAI:
        """Create the default Gemini client after confirming credentials are present."""
        if not os.getenv("GOOGLE_API_KEY"):
            raise DataEngineerAgentError(
                "GOOGLE_API_KEY is not set. Export it before running askdata."
            )
        return ChatGoogleGenerativeAI(
            model=os.getenv("ASKDATA_GOOGLE_MODEL", self.config.model),
            temperature=self.config.temperature,
            thinking_level=self.config.thinking_level,
            include_thoughts=self.config.debug,
        )

    @observe(name="DataEngineerAgent._generate_sql")
    def _generate_sql(
        self,
        question: str,
        schema_summary: str,
        *,
        prior_error: str | None = None,
    ) -> tuple[str, str | None]:
        """Prompt the LLM with schema context and return (sql, thinking_tokens | None)."""
        messages = [
            SystemMessage(
                content=(
                    "You translate analytics questions into a single SQLite query. "
                    "Return SQL only. Do not use markdown fences. "
                    "Use only SELECT or WITH queries. Never modify data. "
                    "Prefer explicit column names over SELECT *. "
                    "Use JOINs when the question requires data from multiple tables. "
                    "The Relationships section of the schema shows exact JOIN paths. "
                    "Before writing SQL, reason through: "
                    "(1) which tables contain the needed data, "
                    "(2) the join keys from the Relationships section, "
                    "(3) whether a CTE would simplify a multi-step query. "
                    "Then return only the final SQL — no commentary. "
                    "If the question cannot be answered from the schema, return "
                    "CANNOT_ANSWER. "
                    "Schema:\n"
                    f"{schema_summary}"
                )
            ),
        ]
        for example_question, example_sql in FEW_SHOT_EXAMPLES:
            messages.append(HumanMessage(content=example_question))
            messages.append(AIMessage(content=example_sql))
        messages.append(HumanMessage(content=question))
        if prior_error is not None:
            messages.append(
                HumanMessage(
                    content=(
                        f"The previous SQL you generated failed with this error: "
                        f"{prior_error}\n"
                        "Please fix the SQL and return only the corrected query."
                    )
                )
            )
        # Add Langfuse callback to LLM invocation for automatic prompt/response tracking
        langfuse_cb = get_langfuse_callback()
        callbacks = [langfuse_cb] if langfuse_cb else []
        response = self.llm.invoke(messages, config={"callbacks": callbacks})
        thinking_tokens = self._extract_thinking(response)
        content = self._response_to_text(response)
        sql = self._extract_sql(content)
        if sql == "CANNOT_ANSWER":
            raise DataEngineerAgentError(
                "The model could not answer the question from the available schema."
            )
        return sql, thinking_tokens

    def _extract_thinking(self, response: Any) -> str | None:
        """Pull Gemini thinking-token text from a response, or return None if absent."""
        content = getattr(response, "content", response)
        if not isinstance(content, list):
            return None
        parts: list[str] = [
            str(item["thinking"])
            for item in content
            if isinstance(item, dict)
            and item.get("type") == "thinking"
            and "thinking" in item
        ]
        return "\n".join(parts) if parts else None

    def _response_to_text(self, response: Any) -> str:
        """Normalize non-thinking response content into one stripped text string."""
        content = getattr(response, "content", response)
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = [
                str(item["text"]) if isinstance(item, dict) else str(item)
                for item in content
                if isinstance(item, str)
                or (
                    isinstance(item, dict)
                    and item.get("type") != "thinking"
                    and "text" in item
                )
            ]
            return "\n".join(parts).strip()
        return str(content).strip()

    def _extract_sql(self, content: str) -> str:
        """Handle fenced output and return the first SELECT or WITH statement found."""
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
