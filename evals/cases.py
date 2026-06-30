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
    EvalCase(
        name="seller_order_count",
        question="How many orders does each seller have? Show the top 10 sellers by order count.",
        reference_sql=(
            """
            SELECT
                s.seller_id,
                s.seller_city,
                s.seller_state,
                COUNT(oi.order_id) AS order_count
            FROM sellers s
            JOIN order_items oi ON s.seller_id = oi.seller_id
            GROUP BY s.seller_id, s.seller_city, s.seller_state
            ORDER BY order_count DESC
            LIMIT 10
            """
        ),
        expected_order_by=("order_count DESC",),
    ),
    EvalCase(
        name="top_product_category_all_time",
        question="What is the top product category by total revenue? Include the product category and number of units",
        reference_sql=(
            """
            -- Step 1: Identify the top-selling product category by total revenue
            WITH category_sales AS (
                SELECT
                    p."product category"               AS product_category,
                    SUM(oi.price)                       AS total_sales
                FROM order_items AS oi
                INNER JOIN products AS p
                    ON oi.product_id = p.product_id
                WHERE p."product category" IS NOT NULL
                GROUP BY
                    p."product category"
            ),

            top_category AS (
                SELECT
                    product_category,
                    total_sales
                FROM category_sales
                ORDER BY total_sales DESC
                LIMIT 1
            )

            -- Step 2: Break down the top category's sales by month
            SELECT
                tc.product_category                                              AS product_category,
                strftime('%Y-%m', o.order_purchase_timestamp)                    AS sales_month,
                COUNT(DISTINCT oi.order_id)                                      AS num_orders,
                SUM(oi.price)                                                    AS monthly_sales
            FROM order_items AS oi
            INNER JOIN products AS p
                ON oi.product_id = p.product_id
            INNER JOIN orders AS o
                ON oi.order_id = o.order_id
            INNER JOIN top_category AS tc
                ON p."product category" = tc.product_category
            WHERE o.order_purchase_timestamp IS NOT NULL
            GROUP BY
                tc.product_category,
                strftime('%Y-%m', o.order_purchase_timestamp)
            ORDER BY
                sales_month ASC;
            """
        ),
        expected_order_by=("sales_month ASC",),
    ),
    EvalCase(
        name="top_product_categories_by_revenue",
        question="What are the top 10 product categories by total revenue? Include the product category.",
        reference_sql=(
            """
            SELECT
                p.product_id,
                p.product_category,
                SUM(oi.price) AS total_revenue
            FROM products p
            JOIN order_items oi ON p.product_id = oi.product_id
            GROUP BY p.product_id, p.product_category
            ORDER BY total_revenue DESC
            LIMIT 10
            """
        ),
        expected_order_by=("total_revenue DESC",),
    ),
    EvalCase(
        name="revenue_by_customer_state",
        question="What is the total payment value by customer state? Order by highest revenue.",
        reference_sql=(
            """
            SELECT
                c.customer_state,
                SUM(p.payment_value) AS total_revenue
            FROM customers c
            JOIN orders o ON c.customer_id = o.customer_id
            JOIN payments p ON o.order_id = p.order_id
            GROUP BY c.customer_state
            ORDER BY total_revenue DESC
            """
        ),
        expected_order_by=("total_revenue DESC",),
    ),
)
