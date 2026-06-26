# AskData
A talk to your data application that answers questions and builds charts from user queries.

This data was sourced from [Kaggle](https://www.kaggle.com/datasets/alexpaul9959/dataset-walmart?select=sellers.csv)

## Setup

Install dependencies with:

```bash
uv sync
```

Install and enable the git hooks with:

```bash
uv run pre-commit install
```

Run the configured checks across the full repo with:

```bash
uv run pre-commit run --all-files
```

Create a `.env` file or export the required Google API key:

```bash
export GOOGLE_API_KEY=your_key_here
```

Optional model override:

```bash
export ASKDATA_GOOGLE_MODEL=gemini-2.5-flash
```

## Bootstrap the orders database

Load `data/orders.csv` into a local SQLite database with:

```bash
python scripts/load_orders_to_sqlite.py
```

The script creates `data/orders.db`, recreates the `orders` table on each run, loads the CSV, and prints a validation summary.

Example SQL query to test the database manually:

```sql
SELECT order_status, COUNT(*) AS order_count
FROM orders
GROUP BY order_status
ORDER BY order_count DESC, order_status ASC;
```

## Run tests

Run the focused unit test suite with:

```bash
uv run python -m unittest discover -s tests
```

Run just the eval-related tests with:

```bash
uv run python -m unittest tests.test_evals
```

The current test suite covers:

- SQLite schema inspection
- read-only database enforcement
- SQL validation and blocking of unsafe queries
- Data Engineer agent behavior with injected fake LLM responses
- eval harness scoring for tool-call accuracy and result-query correctness

Planning and progress notes now live under `docs/`, including `docs/TODO.md` and `docs/progress.md`.

## Code quality

The repo uses `pre-commit` with:

- `ruff-check --fix` for Python linting and import sorting
- `ruff-format` for Python formatting
- standard file hygiene hooks for YAML/TOML validation, merge-conflict markers, trailing whitespace, and missing final newlines

## Run evals

The starter eval pipeline lives under [evals](evals) and currently scores the Data Engineer agent on two dimensions:

- tool-call accuracy: whether the agent followed the expected execution path
- query correctness: whether the returned dataframe matches the dataframe produced by a reference SQL query

Run the full eval suite with:

```bash
uv run python -m evals.harness
```

Print JSON output for downstream analysis with:

```bash
uv run python -m evals.harness --json
```

Run a single case by name with:

```bash
uv run python -m evals.harness --case orders_by_status
```

The eval runner uses the real Data Engineer agent, so it requires `GOOGLE_API_KEY` to be exported before execution.

## Run the agents

### Data Engineer Agent

The first implementation slice translates a natural-language question into read-only SQL, validates the SQL, runs it against `data/orders.db`, and prints the generated SQL plus the pandas-style result table.

The implementation now lives under `src/askdata/agents/`.

Example usage:

```bash
uv run askdata "How many orders do we have by status?"
uv run askdata "Show the first 5 delivered orders"
```

The CLI accepts only read-only queries after validation. If the model generates unsafe SQL or references unknown schema, execution is blocked.

You can also test the Data Engineer agent interactively in the notebook at [notebooks/Data Engineer Agent Tests.ipynb](notebooks/Data%20Engineer%20Agent%20Tests.ipynb). After a kernel restart, rerun the setup cells to reload `.env`.

### BI Analyst Agent

Status: planned, not implemented yet.

The BI Analyst agent is intended to take the SQL result DataFrame, generate KPIs, and produce charts with `pandas` and `plotly`.

### Reporting Agent

Status: planned, not implemented yet.

The Reporting agent is intended to combine the analyst outputs into a markdown or PDF-style report with summarized takeaways and embedded visuals.

## Current agent status

- Implemented: Data Engineer Agent
- Planned: BI Analyst Agent
- Planned: Reporting Agent
