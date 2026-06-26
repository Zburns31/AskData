# Progress

## 2026-06-26

- Reorganized the repository by moving planning documents into `docs/` and the Data Engineer implementation into `src/askdata/agents/`.
- Added `pre-commit` repo tooling with Ruff-based Python lint/format hooks plus standard whitespace, merge-conflict, YAML, and TOML checks.
- Documented how to install and run the hooks locally in `README.md`.
- Added `scripts/load_orders_to_sqlite.py` to create `data/orders.db` and load the `orders` table from `data/orders.csv`.
- Verified the bootstrap by loading 99,441 rows and running the initial aggregate query grouped by `order_status`.
- Documented the bootstrap command and example SQL query in `README.md`.
- Added the first Data Engineer agent slice with SQLite schema inspection, read-only SQL validation, OpenAI-backed SQL generation, and a CLI that prints generated SQL plus the pandas result table.
- Added an `evals/` harness with starter cases for delivery-time and order-status questions, scoring tool-call accuracy from agent traces and query correctness against reference SQL outputs.
- Added focused tests for the eval harness and documented how to run the suite plus JSON output mode.
- Tightened eval ordering semantics by replacing the old comparison sort metadata with explicit expected ordering and by preserving row order during DataFrame comparison.
- Added function-level docstrings across the source, eval, script, and test modules to document responsibilities and key implementation behavior.
- Replaced the old trace-similarity eval metric with SQL execution accuracy, so evals now report when generated SQL fails validation or execution and preserve the attempted SQL plus failure stage for debugging.
