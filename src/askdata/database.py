from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "orders.db"


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    data_type: str
    not_null: bool
    default_value: str | None
    is_primary_key: bool


class DatabaseError(RuntimeError):
    pass


class OrdersDatabase:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH

    def ensure_exists(self) -> None:
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"Could not find SQLite database at {self.db_path}. "
                "Run scripts/load_orders_to_sqlite.py first."
            )

    def connect(self) -> sqlite3.Connection:
        self.ensure_exists()
        db_uri = f"file:{quote(str(self.db_path))}?mode=ro"  # Readonly
        connection = sqlite3.connect(db_uri, uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    def list_tables(self) -> list[str]:
        with self.connect() as connection:
            rows = connection.execute("""
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                ORDER BY name ASC
                """).fetchall()
        return [str(row["name"]) for row in rows]

    def get_table_schema(self, table_name: str) -> list[ColumnInfo]:
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
        return {
            table_name: self.get_table_schema(table_name)
            for table_name in self.list_tables()
        }

    def get_schema_summary(self) -> str:
        lines: list[str] = []
        for table_name, columns in self.get_schema_map().items():
            column_summary = ", ".join(
                f"{column.name} {column.data_type}" for column in columns
            )
            lines.append(f"- {table_name}: {column_summary}")
        return "\n".join(lines)

    def execute_query(
        self, sql: str, parameters: dict[str, Any] | None = None
    ) -> pd.DataFrame:
        with self.connect() as connection:
            return pd.read_sql_query(sql, connection, params=parameters or {})
