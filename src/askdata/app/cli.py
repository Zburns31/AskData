from __future__ import annotations

import argparse
import sys

import plotly.io as pio

from askdata.agents.bi_agent import BIAgentError
from askdata.agents.config import AgentConfig
from askdata.agents.data_engineer import DataEngineerAgentError
from askdata.agents.graph import build_graph
from askdata.agents.planner import PlannerAgentError
from askdata.sql.validator import SqlValidationError
from askdata.storage.database import DatabaseError, SQLiteDatabase


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser for a single natural-language analytics question."""
    parser = argparse.ArgumentParser(
        prog="askdata",
        description="Answer analytics questions using the AskData multi-agent pipeline.",
    )
    parser.add_argument(
        "question", nargs="+", help="Natural-language analytics question"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Show thinking tokens emitted by the model",
    )
    parser.add_argument(
        "--no-chart",
        action="store_true",
        default=False,
        help="Skip opening charts in the browser",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the full AskData pipeline (planner → data engineer → BI) and print results."""
    parser = build_parser()
    args = parser.parse_args(argv)
    question = " ".join(args.question).strip()

    config = AgentConfig(debug=args.debug)
    db = SQLiteDatabase()

    try:
        graph = build_graph(config=config, database=db)
        state = graph.invoke({"question": question})
    except (
        DataEngineerAgentError,
        PlannerAgentError,
        BIAgentError,
        DatabaseError,
        FileNotFoundError,
        SqlValidationError,
        ValueError,
    ) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    if state.get("error"):
        print(f"Error: {state['error']}", file=sys.stderr)
        return 1

    sep = "─" * 60
    query_result = state.get("query_result")

    if args.debug and query_result:
        thinking = next(
            (s.payload for s in query_result.trace if s.name == "thinking_tokens"),
            None,
        )
        if thinking:
            print(f"{'Thinking':^60}")
            print(sep)
            print(thinking)
            print()

    if query_result:
        print("Generated SQL:")
        print(sep)
        print(query_result.sql)
        print()
        print("Results:")
        if query_result.dataframe.empty:
            print("(no rows)")
        else:
            print(query_result.dataframe.to_string(index=False))
        print()

    narrative = state.get("narrative", "")
    if narrative:
        print("Insight:")
        print(sep)
        print(narrative)
        print()

    if not args.no_chart:
        for fig in state.get("charts", []):
            pio.show(fig)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
