from __future__ import annotations

from typing import Any

import plotly.graph_objects as go
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from askdata.agents.bi_agent import BIAgent, BIResult
from askdata.agents.config import AgentConfig
from askdata.agents.data_engineer import DataEngineerAgent, DataEngineerAgentError
from askdata.agents.planner import PlannerAgent
from askdata.storage.database import SQLiteDatabase

__all__ = ["AskDataState", "build_graph"]


class AskDataState(TypedDict):
    """Shared state threaded through every node in the AskData graph."""

    question: str
    refined_question: str
    query_result: Any  # QueryExecutionResult | None — avoid circular at type-check time
    charts: list[go.Figure]
    narrative: str
    error: str | None


def _planner_node(
    state: AskDataState, *, planner: PlannerAgent, db: SQLiteDatabase
) -> dict:
    schema_summary = db.get_schema_summary()
    result = planner.run(state["question"], schema_summary)
    return {"refined_question": result.refined_question}


def _data_engineer_node(state: AskDataState, *, agent: DataEngineerAgent) -> dict:
    try:
        result = agent.run(state["refined_question"])
        return {"query_result": result, "error": None}
    except DataEngineerAgentError as exc:
        return {"query_result": None, "error": str(exc)}


def _bi_node(state: AskDataState, *, bi: BIAgent) -> dict:
    result: BIResult = bi.run(state["query_result"])
    return {"charts": list(result.charts), "narrative": result.narrative}


def _should_run_bi(state: AskDataState) -> str:
    """Route to bi_node on success, or END on error."""
    return "bi_node" if state.get("error") is None else END


def build_graph(
    config: AgentConfig | None = None,
    database: SQLiteDatabase | None = None,
):
    """Construct and compile the AskData StateGraph.

    Returns a compiled LangGraph graph ready for `.invoke()`.
    """
    cfg = config or AgentConfig()
    db = database or SQLiteDatabase()

    planner = PlannerAgent(config=cfg)
    data_engineer = DataEngineerAgent(database=db, config=cfg)
    bi = BIAgent(config=cfg)

    graph = StateGraph(AskDataState)

    graph.add_node(
        "planner_node",
        lambda state: _planner_node(state, planner=planner, db=db),
    )
    graph.add_node(
        "data_engineer_node",
        lambda state: _data_engineer_node(state, agent=data_engineer),
    )
    graph.add_node(
        "bi_node",
        lambda state: _bi_node(state, bi=bi),
    )

    graph.add_edge(START, "planner_node")
    graph.add_edge("planner_node", "data_engineer_node")
    graph.add_conditional_edges("data_engineer_node", _should_run_bi)
    graph.add_edge("bi_node", END)

    return graph.compile()
