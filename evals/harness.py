"""
TODO: Use LLM as a judge to score the correctness of the SQL query and the results, instead of relying on a reference SQL query.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from typing import Any, Callable

import pandas as pd
from pandas.testing import assert_frame_equal

from askdata.agents import (
    DataEngineerAgent,
    DataEngineerAgentError,
    QueryExecutionResult,
)
from askdata.storage.database import SQLiteDatabase
from evals.cases import DEFAULT_EVAL_CASES, EvalCase


@dataclass(frozen=True)
class EvalMetrics:
    sql_execution_accuracy: float
    query_correctness: float
    overall_score: float


@dataclass(frozen=True)
class EvalResult:
    case_name: str
    question: str
    metrics: EvalMetrics
    passed: bool
    actual_sql: str | None
    expected_sql: str
    actual_trace_steps: tuple[str, ...]
    error_type: str | None
    error_message: str | None
    details: tuple[str, ...]


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser for selecting eval cases and output format."""
    parser = argparse.ArgumentParser(
        prog="python -m evals.harness",
        description="Run AskData eval cases against the Data Engineer agent.",
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="cases",
        help="Run only the named eval case. Can be passed multiple times.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON output.",
    )
    return parser


def normalize_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Standardize column names and numeric dtypes before comparing results."""
    normalized = dataframe.copy()
    normalized.columns = [f"column_{index}" for index in range(len(normalized.columns))]
    for column in normalized.select_dtypes(include="number").columns:
        normalized[column] = normalized[column].astype(float)
    return normalized.reset_index(drop=True)


def score_sql_execution(error: Exception | None) -> tuple[float, tuple[str, ...]]:
    """Score whether the generated SQL validated and executed successfully."""
    if error is None:
        return 1.0, ()
    return 0.0, (f"{type(error).__name__}: {error}",)


def score_query_correctness(
    actual: pd.DataFrame, expected: pd.DataFrame
) -> tuple[float, tuple[str, ...]]:
    """Compare actual and expected DataFrames and return a score plus mismatch details."""
    normalized_actual = normalize_dataframe(actual)
    normalized_expected = normalize_dataframe(expected)

    try:
        assert_frame_equal(
            normalized_actual,
            normalized_expected,
            check_dtype=False,
            check_like=False,
            atol=1e-4,
            rtol=1e-4,
        )
    except AssertionError as error:
        return 0.0, (str(error),)

    return 1.0, ()


def run_eval_case(
    case: EvalCase,
    agent_factory: Callable[[], DataEngineerAgent] | None = None,
    database: SQLiteDatabase | None = None,
) -> EvalResult:
    """Run one eval case end to end and aggregate trace and query metrics."""
    database = database or SQLiteDatabase()
    agent = agent_factory() if agent_factory else DataEngineerAgent(database=database)
    expected_dataframe = database.execute_query(case.reference_sql)

    run_error: Exception | None = None
    result: QueryExecutionResult | None = None
    actual_sql: str | None = None
    actual_trace_steps: tuple[str, ...] = ()

    try:
        result = agent.run(case.question)
        actual_sql = result.sql
        actual_trace_steps = tuple(step.name for step in result.trace)
    except DataEngineerAgentError as error:
        run_error = error
        actual_sql = error.sql
        actual_trace_steps = tuple(step.name for step in error.trace)
    except Exception as error:
        run_error = error

    sql_execution_accuracy, sql_execution_details = score_sql_execution(run_error)
    if result is None:
        query_correctness = 0.0
        query_details = ()
    else:
        query_correctness, query_details = score_query_correctness(
            result.dataframe, expected_dataframe
        )

    overall_score = (sql_execution_accuracy + query_correctness) / 2

    details = sql_execution_details + query_details
    if case.expected_order_by and "DataFrame.iloc" in " ".join(query_details):
        details = details + (
            "Expected row ordering "
            f"{case.expected_order_by} to match the reference SQL output.",
        )

    return EvalResult(
        case_name=case.name,
        question=case.question,
        metrics=EvalMetrics(
            sql_execution_accuracy=sql_execution_accuracy,
            query_correctness=query_correctness,
            overall_score=overall_score,
        ),
        passed=sql_execution_accuracy == 1.0 and query_correctness == 1.0,
        actual_sql=actual_sql,
        expected_sql=case.reference_sql,
        actual_trace_steps=actual_trace_steps,
        error_type=type(run_error).__name__ if run_error else None,
        error_message=str(run_error) if run_error else None,
        details=details,
    )


def select_cases(case_names: list[str] | None) -> tuple[EvalCase, ...]:
    """Filter the default eval registry and reject unknown case names early."""
    if not case_names:
        return DEFAULT_EVAL_CASES

    selected = [case for case in DEFAULT_EVAL_CASES if case.name in set(case_names)]
    missing = sorted(set(case_names) - {case.name for case in selected})
    if missing:
        raise ValueError("Unknown eval case(s): " + ", ".join(missing))
    return tuple(selected)


def run_eval_suite(case_names: list[str] | None = None) -> tuple[EvalResult, ...]:
    """Run the selected eval cases against one shared database instance."""
    database = SQLiteDatabase()
    database.ensure_exists()
    return tuple(
        run_eval_case(case, database=database) for case in select_cases(case_names)
    )


def _result_to_dict(result: EvalResult) -> dict[str, Any]:
    """Serialize an EvalResult dataclass tree into plain dictionaries."""
    payload = asdict(result)
    payload["metrics"] = asdict(result.metrics)
    return payload


def _format_summary(results: tuple[EvalResult, ...]) -> str:
    """Render a DataFrame-style summary table for terminal eval output."""
    rows = [
        {
            "case": result.case_name,
            "sql_exec": f"{result.metrics.sql_execution_accuracy:.2f}",
            "correctness": f"{result.metrics.query_correctness:.2f}",
            "overall": f"{result.metrics.overall_score:.2f}",
            "passed": "✓" if result.passed else "✗",
        }
        for result in results
    ]
    summary_df = pd.DataFrame(rows).set_index("case")
    lines = [summary_df.to_string()]

    for result in results:
        if result.details:
            lines.append(f"\n{result.case_name}:")
            for detail in result.details:
                lines.append(f"  {detail}")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments, run evals, and print either JSON or a text summary."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        results = run_eval_suite(args.cases)
    except Exception as error:
        parser.exit(status=1, message=f"Error: {error}\n")

    if args.json:
        print(json.dumps([_result_to_dict(result) for result in results], indent=2))
    else:
        print(_format_summary(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
