from __future__ import annotations

import sqlite3
import unittest

from askdata.database import OrdersDatabase


class OrdersDatabaseTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database = OrdersDatabase()
        try:
            cls.database.ensure_exists()
        except FileNotFoundError as error:
            raise unittest.SkipTest(str(error)) from error

    def test_list_tables_includes_orders(self) -> None:
        self.assertIn("orders", self.database.list_tables())

    def test_execute_query_returns_dataframe(self) -> None:
        dataframe = self.database.execute_query(
            "SELECT order_status, COUNT(*) AS order_count FROM orders GROUP BY order_status"
        )
        self.assertFalse(dataframe.empty)
        self.assertEqual(["order_status", "order_count"], list(dataframe.columns))

    def test_connect_opens_database_in_read_only_mode(self) -> None:
        with self.database.connect() as connection:
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("CREATE TABLE should_fail(id INTEGER)")


if __name__ == "__main__":
    unittest.main()
