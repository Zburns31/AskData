from __future__ import annotations

import unittest

from askdata.sql.validator import SqlValidationError, SqlValidator
from askdata.storage.database import OrdersDatabase


class SqlValidatorTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        """Create the validator fixture once or skip when the SQLite DB is absent."""
        cls.database = OrdersDatabase()
        try:
            cls.database.ensure_exists()
        except FileNotFoundError as error:
            raise unittest.SkipTest(str(error)) from error
        cls.validator = SqlValidator(cls.database)

    def test_allows_aggregate_select(self) -> None:
        """Verify aggregate SELECT queries pass validation unchanged."""
        validated = self.validator.validate(
            "SELECT order_status, COUNT(*) AS order_count FROM orders GROUP BY order_status"
        )
        self.assertIn("FROM orders", validated.sql)

    def test_applies_default_limit_to_row_level_query(self) -> None:
        """Verify row-level queries receive the default LIMIT safeguard."""
        validated = self.validator.validate(
            "SELECT order_id, customer_id FROM orders ORDER BY order_purchase_timestamp DESC"
        )
        self.assertTrue(validated.sql.endswith("LIMIT 200"))

    def test_blocks_non_select_query(self) -> None:
        """Verify mutating statements are rejected before execution."""
        with self.assertRaises(SqlValidationError):
            self.validator.validate("DELETE FROM orders")

    def test_blocks_multi_statement_query(self) -> None:
        """Verify semicolon-separated multi-statement SQL is rejected."""
        with self.assertRaises(SqlValidationError):
            self.validator.validate("SELECT * FROM orders; DROP TABLE orders")

    def test_blocks_unknown_table_reference(self) -> None:
        """Verify references to tables outside the known schema are rejected."""
        with self.assertRaises(SqlValidationError):
            self.validator.validate("SELECT * FROM imaginary_orders")


if __name__ == "__main__":
    unittest.main()
