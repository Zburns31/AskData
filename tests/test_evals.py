from __future__ import annotations

import unittest

from askdata.agents import DataEngineerAgent
from askdata.database import OrdersDatabase
from askdata.validator import SqlValidator
from evals.cases import EvalCase
from evals.harness import run_eval_case, score_tool_call_accuracy
from tests.test_agent import FakeLlm


class EvalHarnessTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database = OrdersDatabase()
        try:
            cls.database.ensure_exists()
        except FileNotFoundError as error:
            raise unittest.SkipTest(str(error)) from error

    def test_scores_perfect_match_for_correct_query_and_trace(self) -> None:
        case = EvalCase(
            name="orders_by_status",
            question="How many orders do we have by status? Order by the most frequent",
            reference_sql=(
                "SELECT order_status, COUNT(*) AS order_count "
                "FROM orders GROUP BY order_status "
                "ORDER BY order_count DESC, order_status ASC"
            ),
            expected_order_by=("order_count DESC", "order_status ASC"),
        )

        result = run_eval_case(
            case,
            agent_factory=lambda: DataEngineerAgent(
                database=self.database,
                validator=SqlValidator(self.database),
                llm=FakeLlm(case.reference_sql),
            ),
            database=self.database,
        )

        self.assertTrue(result.passed)
        self.assertEqual(1.0, result.metrics.tool_call_accuracy)
        self.assertEqual(1.0, result.metrics.query_correctness)

    def test_scores_query_mismatch_when_result_differs_from_reference(self) -> None:
        case = EvalCase(
            name="orders_by_status",
            question="How many orders do we have by status? Order by the most frequent",
            reference_sql=(
                "SELECT order_status, COUNT(*) AS order_count "
                "FROM orders GROUP BY order_status "
                "ORDER BY order_count DESC, order_status ASC"
            ),
            expected_order_by=("order_count DESC", "order_status ASC"),
        )

        result = run_eval_case(
            case,
            agent_factory=lambda: DataEngineerAgent(
                database=self.database,
                validator=SqlValidator(self.database),
                llm=FakeLlm(
                    "SELECT order_status, COUNT(*) AS order_count "
                    "FROM orders WHERE order_status = 'delivered' "
                    "GROUP BY order_status"
                ),
            ),
            database=self.database,
        )

        self.assertFalse(result.passed)
        self.assertEqual(1.0, result.metrics.tool_call_accuracy)
        self.assertEqual(0.0, result.metrics.query_correctness)

    def test_scores_query_mismatch_when_row_order_differs_from_reference(self) -> None:
        case = EvalCase(
            name="orders_by_status",
            question="How many orders do we have by status? Order by the most frequent",
            reference_sql=(
                "SELECT order_status, COUNT(*) AS order_count "
                "FROM orders GROUP BY order_status "
                "ORDER BY order_count DESC, order_status ASC"
            ),
            expected_order_by=("order_count DESC", "order_status ASC"),
        )

        result = run_eval_case(
            case,
            agent_factory=lambda: DataEngineerAgent(
                database=self.database,
                validator=SqlValidator(self.database),
                llm=FakeLlm(
                    "SELECT order_status, COUNT(*) AS order_count "
                    "FROM orders GROUP BY order_status "
                    "ORDER BY order_status ASC"
                ),
            ),
            database=self.database,
        )

        self.assertFalse(result.passed)
        self.assertEqual(0.0, result.metrics.query_correctness)
        self.assertTrue(
            any("Expected row ordering" in detail for detail in result.details)
        )

    def test_scores_perfect_match_when_only_column_aliases_differ(self) -> None:
        case = EvalCase(
            name="orders_by_status",
            question="How many orders do we have by status? Order by the most frequent",
            reference_sql=(
                "SELECT order_status, COUNT(*) AS order_count "
                "FROM orders GROUP BY order_status "
                "ORDER BY order_count DESC, order_status ASC"
            ),
            expected_order_by=("order_count DESC", "order_status ASC"),
        )

        result = run_eval_case(
            case,
            agent_factory=lambda: DataEngineerAgent(
                database=self.database,
                validator=SqlValidator(self.database),
                llm=FakeLlm(
                    "SELECT order_status AS status, COUNT(*) AS total_orders "
                    "FROM orders GROUP BY order_status "
                    "ORDER BY total_orders DESC, status ASC"
                ),
            ),
            database=self.database,
        )

        self.assertTrue(result.passed)
        self.assertEqual(1.0, result.metrics.query_correctness)

    def test_scores_partial_tool_accuracy_for_wrong_trace_order(self) -> None:
        accuracy = score_tool_call_accuracy(
            ("generate_sql", "get_schema_summary", "execute_query"),
            ("get_schema_summary", "generate_sql", "validate_sql", "execute_query"),
        )

        self.assertEqual(0.5, accuracy)


if __name__ == "__main__":
    unittest.main()
