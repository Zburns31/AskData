from __future__ import annotations

from dataclasses import dataclass

DEFAULT_TRACE_STEPS = (
    "get_schema_summary",
    "generate_sql",
    "validate_sql",
    "execute_query",
)


@dataclass(frozen=True)
class EvalCase:
    name: str
    question: str
    reference_sql: str
    expected_trace_steps: tuple[str, ...] = DEFAULT_TRACE_STEPS
    expected_order_by: tuple[str, ...] = ()


DEFAULT_EVAL_CASES: tuple[EvalCase, ...] = (
    EvalCase(
        name="longest_average_delivery_times",
        question="Which order statuses have the longest average delivery times?",
        reference_sql=(
            """
            SELECT
                order_status,
                AVG(JULIANDAY(order_delivered_customer_date) - JULIANDAY(order_purchase_timestamp)) AS average_delivery_time_days
            FROM orders
            WHERE
                order_delivered_customer_date IS NOT NULL
                AND order_purchase_timestamp IS NOT NULL
            GROUP BY order_status
            ORDER BY average_delivery_time_days DESC, order_status ASC
            """
        ),
        expected_order_by=("average_delivery_time_days DESC", "order_status ASC"),
    ),
    EvalCase(
        name="orders_by_status",
        question="How many orders do we have by status? Order by the most frequent",
        reference_sql=(
            """
            SELECT
                order_status, COUNT(order_id) AS order_count
            FROM orders
            GROUP BY order_status
            ORDER BY order_count DESC, order_status ASC
        """
        ),
        expected_order_by=("order_count DESC", "order_status ASC"),
    ),
)
