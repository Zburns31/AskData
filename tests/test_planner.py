from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage

from askdata.agents.config import AgentConfig
from askdata.agents.planner import PlannerAgent, PlannerAgentError, PlannerResult


def _make_planner(response_text: str) -> PlannerAgent:
    llm = MagicMock()
    llm.invoke.return_value = AIMessage(content=response_text)
    return PlannerAgent(llm=llm, config=AgentConfig())


def test_planner_returns_refined_question() -> None:
    planner = _make_planner("What are the top 10 sellers by total order count?")
    result = planner.run(
        "who sells the most?",
        schema_summary="Table: sellers (seller_id, seller_city)\nTable: order_items (seller_id, order_id)",
    )
    assert isinstance(result, PlannerResult)
    assert result.original_question == "who sells the most?"
    assert "seller" in result.refined_question.lower()


def test_planner_preserves_precise_question() -> None:
    precise = "What is the total revenue per product category in 2018?"
    planner = _make_planner(precise)
    result = planner.run(
        precise, schema_summary="Table: products (product_id, product category)"
    )
    assert result.refined_question == precise


def test_planner_raises_on_empty_question() -> None:
    planner = _make_planner("anything")
    with pytest.raises(PlannerAgentError, match="empty"):
        planner.run("   ", schema_summary="Table: orders")


def test_planner_raises_on_empty_llm_response() -> None:
    planner = _make_planner("   ")
    with pytest.raises(PlannerAgentError, match="empty"):
        planner.run("any valid question", schema_summary="Table: orders")
