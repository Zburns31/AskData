from __future__ import annotations

import sqlite3
import unittest

from askdata.storage.database import SQLiteDatabase


class SQLiteDatabaseTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        """Prepare the shared database handle or skip when the fixture is missing."""
        cls.database = SQLiteDatabase()
        try:
            cls.database.ensure_exists()
        except FileNotFoundError as error:
            raise unittest.SkipTest(str(error)) from error

    def test_list_tables_includes_orders(self) -> None:
        """Verify schema discovery includes the bootstrap orders table."""
        self.assertIn("orders", self.database.list_tables())

    def test_execute_query_returns_dataframe(self) -> None:
        """Verify SELECT queries come back as populated pandas DataFrames."""
        dataframe = self.database.execute_query(
            "SELECT order_status, COUNT(*) AS order_count FROM orders GROUP BY order_status"
        )
        self.assertFalse(dataframe.empty)
        self.assertEqual(["order_status", "order_count"], list(dataframe.columns))

    def test_connect_opens_database_in_read_only_mode(self) -> None:
        """Verify write attempts fail because connections are opened in read-only mode."""
        with self.database.connect() as connection:
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("CREATE TABLE should_fail(id INTEGER)")


if __name__ == "__main__":
    unittest.main()
