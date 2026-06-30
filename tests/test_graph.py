from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import plotly.graph_objects as go

from askdata.agents.bi_agent import BIResult
from askdata.agents.config import AgentConfig
from askdata.agents.data_engineer import (
    AgentTraceStep,
    DataEngineerAgentError,
    QueryExecutionResult,
)
from askdata.agents.graph import build_graph
from askdata.agents.planner import PlannerResult

_SCHEMA = "Table: orders (order_id, status)"

_PLANNER_RESULT = PlannerResult(
    original_question="How many orders?",
    refined_question="What is the total number of orders in the database?",
)

_QUERY_RESULT = QueryExecutionResult(
    question=_PLANNER_RESULT.refined_question,
    sql="SELECT COUNT(*) AS total FROM orders",
    dataframe=pd.DataFrame({"total": [42]}),
    trace=(
        AgentTraceStep(
            name="execute_query", payload="SELECT COUNT(*) AS total FROM orders"
        ),
    ),
)

_BI_RESULT = BIResult(
    charts=(go.Figure(),),
    narrative="There are 42 orders in total.",
)


def _make_graph():
    config = AgentConfig()

    with (
        patch("askdata.agents.graph.PlannerAgent") as MockPlanner,
        patch("askdata.agents.graph.DataEngineerAgent") as MockDE,
        patch("askdata.agents.graph.BIAgent") as MockBI,
        patch("askdata.agents.graph.SQLiteDatabase") as MockDB,
    ):
        MockDB.return_value.get_schema_summary.return_value = _SCHEMA
        MockPlanner.return_value.run.return_value = _PLANNER_RESULT
        MockDE.return_value.run.return_value = _QUERY_RESULT
        MockBI.return_value.run.return_value = _BI_RESULT

        graph = build_graph(config=config)
        return graph, MockPlanner, MockDE, MockBI, MockDB


def test_graph_full_pipeline_success() -> None:
    config = AgentConfig()

    with (
        patch("askdata.agents.graph.PlannerAgent") as MockPlanner,
        patch("askdata.agents.graph.DataEngineerAgent") as MockDE,
        patch("askdata.agents.graph.BIAgent") as MockBI,
        patch("askdata.agents.graph.SQLiteDatabase") as MockDB,
    ):
        MockDB.return_value.get_schema_summary.return_value = _SCHEMA
        MockPlanner.return_value.run.return_value = _PLANNER_RESULT
        MockDE.return_value.run.return_value = _QUERY_RESULT
        MockBI.return_value.run.return_value = _BI_RESULT

        graph = build_graph(config=config)
        state = graph.invoke({"question": "How many orders?"})

    assert state["refined_question"] == _PLANNER_RESULT.refined_question
    assert state["query_result"] is _QUERY_RESULT
    assert state["narrative"] == "There are 42 orders in total."
    assert len(state["charts"]) == 1
    assert state.get("error") is None


def test_graph_skips_bi_on_data_engineer_error() -> None:
    config = AgentConfig()

    with (
        patch("askdata.agents.graph.PlannerAgent") as MockPlanner,
        patch("askdata.agents.graph.DataEngineerAgent") as MockDE,
        patch("askdata.agents.graph.BIAgent") as MockBI,
        patch("askdata.agents.graph.SQLiteDatabase") as MockDB,
    ):
        MockDB.return_value.get_schema_summary.return_value = _SCHEMA
        MockPlanner.return_value.run.return_value = _PLANNER_RESULT
        MockDE.return_value.run.side_effect = DataEngineerAgentError("SQL failed")
        MockBI.return_value.run.return_value = _BI_RESULT

        graph = build_graph(config=config)
        state = graph.invoke({"question": "How many orders?"})

    assert state.get("error") == "SQL failed"
    assert state.get("query_result") is None
    # BIAgent should not have been called
    MockBI.return_value.run.assert_not_called()
