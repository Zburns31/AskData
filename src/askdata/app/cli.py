from __future__ import annotations

import argparse
import sys

from askdata.agents import DataEngineerAgent, DataEngineerAgentError
from askdata.sql.validator import SqlValidationError
from askdata.storage.database import DatabaseError


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser for a single natural-language analytics question."""
    parser = argparse.ArgumentParser(
        prog="askdata",
        description="Translate a question into SQL and execute it against orders.db.",
    )
    parser.add_argument(
        "question", nargs="+", help="Natural-language analytics question"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI flow, printing SQL and query results or a user-facing error."""
    parser = build_parser()
    args = parser.parse_args(argv)
    question = " ".join(args.question).strip()

    try:
        result = DataEngineerAgent().run(question)
    except (
        DataEngineerAgentError,
        DatabaseError,
        FileNotFoundError,
        SqlValidationError,
        ValueError,
    ) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print("Generated SQL:")
    print(result.sql)
    print()
    print("Results:")
    if result.dataframe.empty:
        print("(no rows)")
    else:
        print(result.dataframe.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
