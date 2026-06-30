from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import plotly.graph_objects as go
from langchain_core.messages import AIMessage

from askdata.agents.bi_agent import BIAgent, BIResult, _detect_chart_type
from askdata.agents.config import AgentConfig
from askdata.agents.data_engineer import AgentTraceStep, QueryExecutionResult


def _make_query_result(
    df: pd.DataFrame, question: str = "Test question?"
) -> QueryExecutionResult:
    return QueryExecutionResult(
        question=question,
        sql="SELECT 1",
        dataframe=df,
        trace=(AgentTraceStep(name="execute_query", payload="SELECT 1"),),
    )


def _make_bi_agent(narrative: str = "Key insight here.") -> BIAgent:
    llm = MagicMock()
    llm.invoke.return_value = AIMessage(content=narrative)
    return BIAgent(llm=llm, config=AgentConfig())


# --- chart type heuristics ---


def test_detect_chart_type_line_with_datetime() -> None:
    df = pd.DataFrame(
        {
            "date": pd.date_range("2024-01", periods=3, freq="ME"),
            "revenue": [100, 200, 150],
        }
    )
    assert _detect_chart_type(df) == "line"


def test_detect_chart_type_line_with_date_string() -> None:
    df = pd.DataFrame(
        {"month": ["2024-01", "2024-02", "2024-03"], "orders": [10, 20, 15]}
    )
    assert _detect_chart_type(df) == "line"


def test_detect_chart_type_bar_categorical_numeric() -> None:
    df = pd.DataFrame({"category": ["A", "B", "C"], "sales": [1000, 2000, 1500]})
    assert _detect_chart_type(df) == "bar"


def test_detect_chart_type_scatter_two_numerics() -> None:
    df = pd.DataFrame({"price": [10.0, 20.0, 30.0], "quantity": [5, 3, 8]})
    assert _detect_chart_type(df) == "scatter"


def test_detect_chart_type_table_fallback_single_numeric() -> None:
    df = pd.DataFrame({"revenue": [100, 200, 300]})
    assert _detect_chart_type(df) == "table"


# --- BIAgent.run ---


def test_bi_agent_returns_bi_result() -> None:
    agent = _make_bi_agent("Revenue peaked in March.")
    df = pd.DataFrame({"category": ["A", "B"], "sales": [500, 700]})
    result = agent.run(_make_query_result(df))

    assert isinstance(result, BIResult)
    assert len(result.charts) == 1
    assert isinstance(result.charts[0], go.Figure)
    assert result.narrative == "Revenue peaked in March."


def test_bi_agent_handles_empty_dataframe() -> None:
    agent = _make_bi_agent("No data found.")
    df = pd.DataFrame(columns=["category", "sales"])
    result = agent.run(_make_query_result(df))
    assert isinstance(result, BIResult)
    assert result.narrative == "No data found."
