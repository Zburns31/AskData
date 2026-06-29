"""Load all CSV files in the data/ directory into a single SQLite database.

Each CSV becomes a table whose name matches the file stem (e.g. orders.csv →
table `orders`).  Run this script whenever the source data changes; existing
tables are dropped and recreated.

Usage:
    uv run python scripts/load_data.py
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "askdata.db"

# CSV files to skip (e.g. large geo data the agents don't need yet)
SKIP_FILES: set[str] = set()


def load_csv(connection: sqlite3.Connection, csv_path: Path) -> int:
    """Read one CSV into a DataFrame and write it to SQLite, replacing any existing table."""
    table_name = csv_path.stem
    df = pd.read_csv(csv_path, low_memory=False)
    df.to_sql(table_name, connection, if_exists="replace", index=False)
    return len(df)


def main() -> None:
    """Discover all CSVs, load them into askdata.db, and print a summary."""
    csv_files = sorted(p for p in DATA_DIR.glob("*.csv") if p.name not in SKIP_FILES)

    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in {DATA_DIR}")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    print(f"Loading {len(csv_files)} CSV file(s) into {DB_PATH}\n")

    with sqlite3.connect(DB_PATH) as connection:
        for csv_path in csv_files:
            row_count = load_csv(connection, csv_path)
            print(f"  {csv_path.stem:<40} {row_count:>8,} rows")

    print(f"\nDone. Database written to {DB_PATH}")


if __name__ == "__main__":
    main()
