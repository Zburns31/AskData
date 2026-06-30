from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "askdata.db"


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    data_type: str
    not_null: bool
    default_value: str | None
    is_primary_key: bool


class DatabaseError(RuntimeError):
    pass


class SQLiteDatabase:
    def __init__(self, db_path: Path | None = None) -> None:
        """Store the SQLite database path used by later read-only operations."""
        self.db_path = db_path or DEFAULT_DB_PATH

    def ensure_exists(self) -> None:
        """Fail fast when the expected SQLite file has not been created yet."""
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"Could not find SQLite database at {self.db_path}. "
                "Run scripts/load_orders_to_sqlite.py first."
            )

    def connect(self) -> sqlite3.Connection:
        """Open a read-only SQLite connection configured to return row objects."""
        self.ensure_exists()
        db_uri = f"file:{quote(str(self.db_path))}?mode=ro"  # Readonly
        connection = sqlite3.connect(db_uri, uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    def list_tables(self) -> list[str]:
        """Query sqlite_master and return table names in deterministic order."""
        with self.connect() as connection:
            rows = connection.execute("""
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                ORDER BY name ASC
                """).fetchall()
        return [str(row["name"]) for row in rows]

    def get_table_schema(self, table_name: str) -> list[ColumnInfo]:
        """Read PRAGMA metadata for one table and map each row into ColumnInfo."""
        with self.connect() as connection:
            rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()

        if not rows:
            raise DatabaseError(
                f"Table '{table_name}' does not exist in {self.db_path}"
            )

        return [
            ColumnInfo(
                name=str(row["name"]),
                data_type=str(row["type"]),
                not_null=bool(row["notnull"]),
                default_value=row["dflt_value"],
                is_primary_key=bool(row["pk"]),
            )
            for row in rows
        ]

    def get_schema_map(self) -> dict[str, list[ColumnInfo]]:
        """Build a table-to-columns mapping by inspecting every discovered table."""
        return {
            table_name: self.get_table_schema(table_name)
            for table_name in self.list_tables()
        }

    def get_schema_relationships(self) -> list[str]:
        """Auto-detect JOIN relationships by matching shared column names across tables.

        For each column name that appears in more than one table, the table whose
        column is flagged as a primary key is treated as the "primary" side of the
        join.  Where no primary key is flagged, the first table in alphabetical order
        is used as the left side so the output is deterministic.
        """
        schema_map = self.get_schema_map()

        # Map column_name → list of (table_name, is_primary_key)
        col_to_tables: dict[str, list[tuple[str, bool]]] = {}
        for table_name, columns in schema_map.items():
            for col in columns:
                col_to_tables.setdefault(col.name, []).append(
                    (table_name, col.is_primary_key)
                )

        relationships: list[str] = []
        seen: set[frozenset[str]] = set()
        for col_name, table_entries in col_to_tables.items():
            if len(table_entries) < 2:
                continue
            # Identify the primary (PK) table; fall back to alphabetical first
            pk_tables = [t for t, is_pk in table_entries if is_pk]
            all_tables = sorted(t for t, _ in table_entries)
            primary = pk_tables[0] if pk_tables else all_tables[0]
            for other_table, _ in table_entries:
                if other_table == primary:
                    continue
                pair = frozenset({primary, other_table})
                if pair in seen:
                    continue
                seen.add(pair)
                relationships.append(
                    f"- {primary} JOIN {other_table}"
                    f" ON {primary}.{col_name} = {other_table}.{col_name}"
                )

        return sorted(relationships)

    def get_schema_summary(self) -> str:
        """Render the schema map into a compact text summary for prompt context."""
        lines: list[str] = []
        for table_name, columns in self.get_schema_map().items():
            column_summary = ", ".join(
                f"{column.name} {column.data_type}" for column in columns
            )
            lines.append(f"- {table_name}: {column_summary}")

        relationships = self.get_schema_relationships()
        if relationships:
            lines.append("\nRelationships:")
            lines.extend(relationships)

        return "\n".join(lines)

    def execute_query(
        self, sql: str, parameters: dict[str, Any] | None = None
    ) -> pd.DataFrame:
        """Execute a validated SQL query and return the result as a DataFrame."""
        with self.connect() as connection:
            return pd.read_sql_query(sql, connection, params=parameters or {})
