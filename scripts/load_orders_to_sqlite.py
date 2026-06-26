from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = PROJECT_ROOT / "data" / "orders.csv"
DB_PATH = PROJECT_ROOT / "data" / "orders.db"

TABLE_NAME = "orders"
COLUMNS = [
    "order_id",
    "customer_id",
    "order_status",
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
]


def create_orders_table(connection: sqlite3.Connection) -> None:
    """Recreate the orders table so the load starts from a known schema."""
    connection.execute(f"DROP TABLE IF EXISTS {TABLE_NAME}")
    connection.execute(f"""
        CREATE TABLE {TABLE_NAME} (
            order_id TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL,
            order_status TEXT NOT NULL,
            order_purchase_timestamp TEXT,
            order_approved_at TEXT,
            order_delivered_carrier_date TEXT,
            order_delivered_customer_date TEXT,
            order_estimated_delivery_date TEXT
        )
        """)


def normalize_row(row: dict[str, str]) -> tuple[str | None, ...]:
    """Convert CSV dict values into the ordered tuple expected by INSERTs."""
    return tuple(row[column] or None for column in COLUMNS)


def load_orders(connection: sqlite3.Connection, csv_path: Path) -> int:
    """Read the CSV file, normalize each row, and bulk insert it into SQLite."""
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = [normalize_row(row) for row in reader]

    placeholders = ", ".join("?" for _ in COLUMNS)
    columns_sql = ", ".join(COLUMNS)
    connection.executemany(
        f"INSERT INTO {TABLE_NAME} ({columns_sql}) VALUES ({placeholders})",
        rows,
    )
    return len(rows)


def fetch_status_counts(connection: sqlite3.Connection) -> list[tuple[str, int]]:
    """Run a sample aggregate query used to verify the loaded table contents."""
    cursor = connection.execute(f"""
        SELECT order_status, COUNT(*) AS order_count
        FROM {TABLE_NAME}
        GROUP BY order_status
        ORDER BY order_count DESC, order_status ASC
        """)
    return [(status, count) for status, count in cursor.fetchall()]


def main() -> None:
    """Build the SQLite database from CSV and print a small verification report."""
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"Could not find source CSV at {CSV_PATH}")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH) as connection:
        create_orders_table(connection)
        inserted_rows = load_orders(connection, CSV_PATH)
        total_rows = connection.execute(
            f"SELECT COUNT(*) FROM {TABLE_NAME}"
        ).fetchone()[0]
        status_counts = fetch_status_counts(connection)
        connection.commit()

    print(f"Created SQLite database at: {DB_PATH}")
    print(f"Loaded {inserted_rows} rows into '{TABLE_NAME}'.")
    print(f"Verified total rows: {total_rows}")
    print("Example query result: order counts by status")
    for status, count in status_counts:
        print(f"- {status}: {count}")


if __name__ == "__main__":
    main()
