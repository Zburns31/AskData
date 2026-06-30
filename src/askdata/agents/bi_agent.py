from __future__ import annotations

import os
from dataclasses import dataclass

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from askdata.agents.config import AgentConfig
from askdata.agents.data_engineer import QueryExecutionResult
from askdata.observability import get_langfuse_callback, observe

__all__ = ["BIAgent", "BIAgentError", "BIResult"]

_NARRATIVE_SYSTEM_PROMPT = """\
You are a business intelligence analyst. Given a user question, a SQL query, and a
summary of the query results, write 2-3 sentences that clearly answer the question
and highlight the most important insight from the data.

Rules:
- Be concise and factual. Reference specific numbers from the data.
- Do not describe the chart or explain how you computed the answer.
- Do not repeat the question verbatim.
- Write in plain prose. No bullet points or markdown.
"""


@dataclass(frozen=True)
class BIResult:
    charts: tuple[go.Figure, ...]
    narrative: str


class BIAgentError(RuntimeError):
    pass


def _detect_chart_type(df: pd.DataFrame) -> str:
    """Heuristic: pick the most appropriate chart type for the given DataFrame."""
    # Detect datetime columns
    datetime_cols = [
        c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])
    ]
    # Also check string columns that look like dates (YYYY-MM or YYYY-MM-DD)
    if not datetime_cols:
        for col in df.select_dtypes(include="object").columns:
            sample = df[col].dropna().head(5)
            if sample.str.match(r"^\d{4}-\d{2}").all():
                datetime_cols.append(col)
                break

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    categorical_cols = [
        c for c in df.columns if c not in numeric_cols and c not in datetime_cols
    ]

    if datetime_cols and numeric_cols:
        return "line"
    if categorical_cols and numeric_cols:
        return "bar"
    if len(numeric_cols) >= 2:
        return "scatter"
    return "table"


def _build_chart(df: pd.DataFrame, question: str) -> go.Figure:
    """Build a Plotly figure using heuristics on the DataFrame shape."""
    if df.empty:
        return go.Figure().update_layout(title="No data returned")

    chart_type = _detect_chart_type(df)
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    non_numeric_cols = [c for c in df.columns if c not in numeric_cols]

    if chart_type == "line":
        x_col = non_numeric_cols[0] if non_numeric_cols else df.columns[0]
        y_col = numeric_cols[0]
        fig = px.line(df, x=x_col, y=y_col, title=question)

    elif chart_type == "bar":
        x_col = non_numeric_cols[0]
        y_col = numeric_cols[0]
        # Limit to top 25 rows for readability
        plot_df = df.head(25)
        fig = px.bar(plot_df, x=x_col, y=y_col, title=question)

    elif chart_type == "scatter":
        fig = px.scatter(df, x=numeric_cols[0], y=numeric_cols[1], title=question)

    else:
        # Fallback: render as a plain table figure
        fig = go.Figure(
            data=[
                go.Table(
                    header=dict(values=list(df.columns)),
                    cells=dict(values=[df[c] for c in df.columns]),
                )
            ]
        ).update_layout(title=question)

    return fig


def _dataframe_summary(df: pd.DataFrame, max_rows: int = 10) -> str:
    """Produce a compact text representation of the DataFrame for LLM context."""
    lines = [f"Rows: {len(df)}", f"Columns: {', '.join(df.columns)}"]
    lines.append(df.head(max_rows).to_string(index=False))
    return "\n".join(lines)


class BIAgent:
    """Turns a QueryExecutionResult into charts and a natural-language narrative."""

    def __init__(
        self,
        llm: object | None = None,
        config: AgentConfig | None = None,
    ) -> None:
        self.config = config or AgentConfig()
        self.llm = llm or self._build_default_llm()

    @observe(name="BIAgent.run")
    def run(self, result: QueryExecutionResult) -> BIResult:
        """Generate chart(s) and a narrative for *result*."""
        chart = _build_chart(result.dataframe, result.question)
        narrative = self._generate_narrative(result)
        return BIResult(charts=(chart,), narrative=narrative)

    @observe(name="BIAgent._generate_narrative")
    def _generate_narrative(self, result: QueryExecutionResult) -> str:
        summary = _dataframe_summary(result.dataframe)
        messages = [
            SystemMessage(content=_NARRATIVE_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"Question: {result.question}\n\n"
                    f"SQL:\n{result.sql}\n\n"
                    f"Data:\n{summary}"
                )
            ),
        ]
        callbacks = [cb for cb in [get_langfuse_callback()] if cb is not None]
        response = self.llm.invoke(messages, config={"callbacks": callbacks})
        raw = response.content
        return (
            "".join(p if isinstance(p, str) else p.get("text", "") for p in raw)
            if isinstance(raw, list)
            else raw
        ).strip()

    def _build_default_llm(self) -> ChatGoogleGenerativeAI:
        if not os.getenv("GOOGLE_API_KEY"):
            raise BIAgentError(
                "GOOGLE_API_KEY is not set. Export it before running askdata."
            )
        return ChatGoogleGenerativeAI(
            model=os.getenv("ASKDATA_GOOGLE_MODEL", self.config.model),
            temperature=self.config.temperature,
        )
