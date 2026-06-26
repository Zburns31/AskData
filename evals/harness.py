from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from typing import Any, Callable

import pandas as pd
from pandas.testing import assert_frame_equal

from askdata.agents import DataEngineerAgent, QueryExecutionResult
from askdata.database import OrdersDatabase
from evals.cases import DEFAULT_EVAL_CASES, EvalCase


@dataclass(frozen=True)
class EvalMetrics:
    tool_call_accuracy: float
    query_correctness: float
    overall_score: float


@dataclass(frozen=True)
class EvalResult:
    case_name: str
    question: str
    metrics: EvalMetrics
    passed: bool
    actual_sql: str
    expected_sql: str
    actual_trace_steps: tuple[str, ...]
    expected_trace_steps: tuple[str, ...]
    details: tuple[str, ...]


def build_parser() -> argparse.ArgumentParser:
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
    normalized = dataframe.copy()
    normalized.columns = [f"column_{index}" for index in range(len(normalized.columns))]
    for column in normalized.select_dtypes(include="number").columns:
        normalized[column] = normalized[column].astype(float)
    return normalized.reset_index(drop=True)


def score_tool_call_accuracy(
    actual_steps: tuple[str, ...], expected_steps: tuple[str, ...]
) -> float:
    if not actual_steps and not expected_steps:
        return 1.0

    if not actual_steps or not expected_steps:
        return 0.0

    longest_common_subsequence = [[0] * (len(expected_steps) + 1)]
    for actual_step in actual_steps:
        current_row = [0]
        for index, expected_step in enumerate(expected_steps, start=1):
            if actual_step == expected_step:
                current_row.append(longest_common_subsequence[-1][index - 1] + 1)
            else:
                current_row.append(
                    max(current_row[-1], longest_common_subsequence[-1][index])
                )
        longest_common_subsequence.append(current_row)

    total_positions = max(len(actual_steps), len(expected_steps))
    return longest_common_subsequence[-1][-1] / total_positions


def score_query_correctness(
    actual: pd.DataFrame, expected: pd.DataFrame
) -> tuple[float, tuple[str, ...]]:
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
    database: OrdersDatabase | None = None,
) -> EvalResult:
    database = database or OrdersDatabase()
    agent = agent_factory() if agent_factory else DataEngineerAgent(database=database)
    result: QueryExecutionResult = agent.run(case.question)
    expected_dataframe = database.execute_query(case.reference_sql)

    actual_trace_steps = tuple(step.name for step in result.trace)
    tool_call_accuracy = score_tool_call_accuracy(
        actual_trace_steps, case.expected_trace_steps
    )
    query_correctness, query_details = score_query_correctness(
        result.dataframe, expected_dataframe
    )
    overall_score = (tool_call_accuracy + query_correctness) / 2

    details = query_details
    if tool_call_accuracy < 1.0:
        details = details + (
            "Expected trace steps "
            f"{case.expected_trace_steps} but saw {actual_trace_steps}.",
        )
    if case.expected_order_by and "DataFrame.iloc" in " ".join(query_details):
        details = details + (
            "Expected row ordering "
            f"{case.expected_order_by} to match the reference SQL output.",
        )

    return EvalResult(
        case_name=case.name,
        question=case.question,
        metrics=EvalMetrics(
            tool_call_accuracy=tool_call_accuracy,
            query_correctness=query_correctness,
            overall_score=overall_score,
        ),
        passed=tool_call_accuracy == 1.0 and query_correctness == 1.0,
        actual_sql=result.sql,
        expected_sql=case.reference_sql,
        actual_trace_steps=actual_trace_steps,
        expected_trace_steps=case.expected_trace_steps,
        details=details,
    )


def select_cases(case_names: list[str] | None) -> tuple[EvalCase, ...]:
    if not case_names:
        return DEFAULT_EVAL_CASES

    selected = [case for case in DEFAULT_EVAL_CASES if case.name in set(case_names)]
    missing = sorted(set(case_names) - {case.name for case in selected})
    if missing:
        raise ValueError("Unknown eval case(s): " + ", ".join(missing))
    return tuple(selected)


def run_eval_suite(case_names: list[str] | None = None) -> tuple[EvalResult, ...]:
    database = OrdersDatabase()
    database.ensure_exists()
    return tuple(
        run_eval_case(case, database=database) for case in select_cases(case_names)
    )


def _result_to_dict(result: EvalResult) -> dict[str, Any]:
    payload = asdict(result)
    payload["metrics"] = asdict(result.metrics)
    return payload


def _format_summary(results: tuple[EvalResult, ...]) -> str:
    lines = [
        "case | tool_call_accuracy | query_correctness | overall_score | passed",
        "-" * 72,
    ]
    for result in results:
        lines.append(
            " | ".join(
                [
                    result.case_name,
                    f"{result.metrics.tool_call_accuracy:.2f}",
                    f"{result.metrics.query_correctness:.2f}",
                    f"{result.metrics.overall_score:.2f}",
                    "yes" if result.passed else "no",
                ]
            )
        )
        if result.details:
            for detail in result.details:
                lines.append(f"  detail: {detail}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
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
