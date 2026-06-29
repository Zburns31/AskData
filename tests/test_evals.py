from __future__ import annotations

import unittest

from askdata.agents import DataEngineerAgent
from askdata.sql.validator import SqlValidator
from askdata.storage.database import SQLiteDatabase
from evals.cases import EvalCase
from evals.harness import run_eval_case
from tests.test_agent import FakeLlm


class EvalHarnessTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        """Prepare a reusable database fixture or skip when it does not exist."""
        cls.database = SQLiteDatabase()
        try:
            cls.database.ensure_exists()
        except FileNotFoundError as error:
            raise unittest.SkipTest(str(error)) from error

    def test_scores_perfect_match_for_correct_query_and_trace(self) -> None:
        """Verify a matching query and expected trace produce a fully passing eval."""
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
        self.assertEqual(1.0, result.metrics.sql_execution_accuracy)
        self.assertEqual(1.0, result.metrics.query_correctness)

    def test_scores_query_mismatch_when_result_differs_from_reference(self) -> None:
        """Verify result mismatches zero out query correctness even with the right trace."""
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
        self.assertEqual(1.0, result.metrics.sql_execution_accuracy)
        self.assertEqual(0.0, result.metrics.query_correctness)

    def test_scores_query_mismatch_when_row_order_differs_from_reference(self) -> None:
        """Verify row ordering differences are reported when ordered outputs do not match."""
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
        """Verify alias-only differences do not change the result correctness score."""
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

    def test_scores_invalid_sql_as_execution_failure(self) -> None:
        """Verify invalid SQL is captured as an execution failure instead of a trace miss."""
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
                llm=FakeLlm("SELECT missing_column FROM orders"),
            ),
            database=self.database,
        )

        self.assertFalse(result.passed)
        self.assertEqual(0.0, result.metrics.sql_execution_accuracy)
        self.assertEqual(0.0, result.metrics.query_correctness)
        self.assertEqual("SELECT missing_column FROM orders", result.actual_sql)
        self.assertEqual("DataEngineerAgentError", result.error_type)
        self.assertIn("validate_sql_error", result.actual_trace_steps)


if __name__ == "__main__":
    unittest.main()
