from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from askdata.storage.database import SQLiteDatabase

FORBIDDEN_KEYWORDS = {
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "attach",
    "detach",
    "pragma",
    "create",
    "replace",
    "truncate",
    "vacuum",
    "reindex",
}

ROW_LEVEL_FUNCTION_HINTS = ("count(", "sum(", "avg(", "min(", "max(")


class SqlValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedQuery:
    sql: str
    referenced_tables: tuple[str, ...]


class SqlValidator:
    def __init__(self, database: SQLiteDatabase, default_limit: int = 200) -> None:
        """Bind the database used for schema checks and the fallback row limit."""
        self.database = database
        self.default_limit = default_limit

    def validate(self, sql: str) -> ValidatedQuery:
        """Normalize, safety-check, and compile-test a query before execution."""
        normalized_sql = self._normalize_sql(sql)
        self._ensure_single_statement(normalized_sql)
        self._ensure_read_only(normalized_sql)
        referenced_tables = self._extract_referenced_tables(normalized_sql)
        self._ensure_known_tables(normalized_sql, referenced_tables)
        limited_sql = self._apply_default_limit(normalized_sql)
        self._dry_run_compile(limited_sql)
        return ValidatedQuery(
            sql=limited_sql, referenced_tables=tuple(referenced_tables)
        )

    def _normalize_sql(self, sql: str) -> str:
        """Trim outer whitespace and collapse internal runs into single spaces."""
        normalized_sql = sql.strip()
        if not normalized_sql:
            raise SqlValidationError("SQL query is empty.")
        return re.sub(r"\s+", " ", normalized_sql)

    def _ensure_single_statement(self, sql: str) -> None:
        """Reject semicolon-separated or syntactically incomplete SQL statements."""
        if ";" in sql:
            raise SqlValidationError("Multi-statement queries are not allowed.")
        if not sqlite3.complete_statement(f"{sql};"):
            raise SqlValidationError("SQL query appears to be incomplete.")

    def _ensure_read_only(self, sql: str) -> None:
        """Allow only SELECT-style queries and block mutating SQL keywords."""
        lowered_sql = sql.lower()
        if not lowered_sql.startswith(("select ", "with ")):
            raise SqlValidationError("Only SELECT and WITH queries are allowed.")

        for keyword in FORBIDDEN_KEYWORDS:
            if re.search(rf"\b{keyword}\b", lowered_sql):
                raise SqlValidationError(f"Forbidden SQL keyword detected: {keyword}")

    def _extract_referenced_tables(self, sql: str) -> list[str]:
        """Collect table names mentioned after FROM and JOIN clauses in order."""
        pattern = re.compile(r"\b(?:from|join)\s+([a-zA-Z_][\w]*)", re.IGNORECASE)
        return list(dict.fromkeys(match.group(1) for match in pattern.finditer(sql)))

    def _ensure_known_tables(self, sql: str, referenced_tables: list[str]) -> None:
        """Verify that every referenced table is either in SQLite or declared as a CTE."""
        if not referenced_tables:
            raise SqlValidationError(
                "Could not determine the table referenced by the query."
            )

        known_tables = set(self.database.list_tables())
        cte_names = self._extract_cte_names(sql)
        unknown_tables = [
            table
            for table in referenced_tables
            if table not in known_tables and table not in cte_names
        ]
        if unknown_tables:
            raise SqlValidationError(
                f"Unknown table(s) referenced: {', '.join(unknown_tables)}"
            )

    def _extract_cte_names(self, sql: str) -> set[str]:
        """Parse WITH clause aliases so CTEs are not mistaken for unknown tables."""
        pattern = re.compile(r"\bwith\b.*?\b(\w+)\s+as\s*\(", re.IGNORECASE | re.DOTALL)
        return {match.group(1) for match in pattern.finditer(sql)}

    def _apply_default_limit(self, sql: str) -> str:
        """Append a LIMIT to row-level queries while leaving aggregates untouched."""
        lowered_sql = sql.lower()
        if " limit " in lowered_sql:
            return sql
        if " group by " in lowered_sql or any(
            function_hint in lowered_sql for function_hint in ROW_LEVEL_FUNCTION_HINTS
        ):
            return sql
        return f"{sql} LIMIT {self.default_limit}"

    def _dry_run_compile(self, sql: str) -> None:
        """Compile the query inside a subquery to catch schema and syntax errors safely."""
        dry_run_sql = f"SELECT * FROM ({sql}) AS validated_query LIMIT 0"
        try:
            with self.database.connect() as connection:
                connection.execute(dry_run_sql)
        except sqlite3.Error as error:
            raise SqlValidationError(
                f"SQL failed validation against the schema: {error}"
            ) from error
