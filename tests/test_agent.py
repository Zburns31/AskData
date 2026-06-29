from __future__ import annotations

import unittest

from askdata.agents import DataEngineerAgent
from askdata.sql.validator import SqlValidator
from askdata.storage.database import SQLiteDatabase


class FakeResponse:
    def __init__(self, content: str) -> None:
        """Store fake model output in the attribute shape LangChain responses use."""
        self.content = content


class FakeLlm:
    def __init__(self, content: str) -> None:
        """Capture the canned response text returned for every invocation."""
        self.content = content

    def invoke(self, messages: object) -> FakeResponse:
        """Ignore prompt messages and return the preconfigured fake response."""
        return FakeResponse(self.content)


class DataEngineerAgentTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        """Skip the suite when the fixture database has not been generated yet."""
        cls.database = SQLiteDatabase()
        try:
            cls.database.ensure_exists()
        except FileNotFoundError as error:
            raise unittest.SkipTest(str(error)) from error

    def test_executes_validated_sql_from_llm_output(self) -> None:
        """Verify the agent validates generated SQL, executes it, and records its trace."""
        agent = DataEngineerAgent(
            database=self.database,
            validator=SqlValidator(self.database),
            llm=FakeLlm(
                "SELECT order_status, COUNT(*) AS order_count FROM orders GROUP BY order_status ORDER BY order_count DESC"
            ),
        )
        result = agent.run("How many orders do we have by status?")
        self.assertEqual(
            ["order_status", "order_count"],
            list(result.dataframe.columns),
        )
        self.assertIn("GROUP BY order_status", result.sql)
        self.assertEqual(
            [
                "get_schema_summary",
                "generate_sql",
                "validate_sql",
                "execute_query",
            ],
            [step.name for step in result.trace],
        )

    def test_extracts_sql_from_fenced_response(self) -> None:
        """Verify fenced SQL is unwrapped before validation adds the default LIMIT."""
        agent = DataEngineerAgent(
            database=self.database,
            validator=SqlValidator(self.database),
            llm=FakeLlm("```sql\nSELECT order_id FROM orders\n```"),
        )
        result = agent.run("Show one order id")
        self.assertIn("LIMIT 200", result.sql)


if __name__ == "__main__":
    unittest.main()
