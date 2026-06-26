# TODO

## Multi-Agent Architecture Experiment

Let's try using a multi-agent architecture:

## Goal

Build a local, read-only analytics agent that can:

- accept a natural-language business question,
- translate it into safe SQL against `data/orders.db`,
- analyze the returned data,
- generate charts and KPI summaries,
- assemble the result into a clean markdown report.

The first version should run locally from the CLI and use the existing SQLite database created by `scripts/load_orders_to_sqlite.py`.

## Why This Architecture

- It separates SQL generation from analysis and presentation.
- It reduces the chance that one agent tries to do too much in a single prompt.
- It gives us clearer validation points for SQL safety, chart generation, and report quality.
- It creates a natural path to future extensions such as notebook export, PDF export, or an MCP wrapper.

## Phase 1 Scope

- Single database: `data/orders.db`
- Single table required for v1: `orders`
- Read-only execution only
- CLI-first user experience
- Markdown report output required
- Chart image export optional for the first pass if interactive Plotly HTML is easier

## Non-Goals For V1

- Multi-user sessions
- Long-running memory across conversations
- Multi-database joins
- Web app integration
- Fully autonomous chart selection for every possible question

## V2 Goals
- Implement LLM as a judge to score agent generated sql
- Switch to using local models via Ollama

### 1. The Data Engineer Agent

- **Role:** Translates the user's natural language request into a precise SQL query.
- **Tools:** Read-only Database Tool, Schema Inspector Tool.
- **Guardrails:** Strictly restricted to `SELECT` statements. It must match user requests against a cached database schema or vector index of table definitions to avoid hallucinating column names.
- **References:** [1](https://techcommunity.microsoft.com/blog/adformysql/tutorial-building-ai-agents-that-talk-to-your-azure-database-for-mysql/4504995), [2](https://medium.com/data-science-collective/introduction-to-sql-ai-agents-the-four-components-behind-natural-language-sql-99cb40e72719), [3](https://builder.ai2sql.io/blog/sql-for-product-managers)

#### Implementation Notes

- Input: user question plus a compact schema summary.
- Output: a single SQL query plus a brief reasoning string.
- Query style: SQLite-compatible SQL only.
- Fallback behavior: if the request cannot be answered from the known schema, return a structured failure instead of guessing.

#### Required Guardrails

- Allow only a single statement.
- Allow only queries beginning with `SELECT` or `WITH`.
- Reject `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `ATTACH`, `PRAGMA`, and semicolon-separated multi-statement input.
- Enforce a row limit if the query does not include one.
- Validate referenced table and column names against cached schema metadata before execution.

#### Deliverables

- Schema cache builder for SQLite metadata.
- Query validator for read-only enforcement.
- Agent prompt template for SQL generation.
- Unit tests covering allowed and blocked SQL patterns.

### 2. The BI Analyst Agent

- **Role:** Transforms raw SQL tabular results into meaningful insights and visual assets.
- **Tools:** Python Code Sandbox Tool (`pandas`, `matplotlib`, `seaborn`, `plotly`).
- **Execution:** It writes a localized Python script to generate charts, such as saving a `sales_trend.png` line chart, and calculates key performance indicators like month-over-month growth.
- **References:** [1](https://sqlpad.io/tutorial/ultimate-guide-master-sql-for-data-science/), [2](https://engineering.fb.com/2022/04/26/developer-tools/sql-notebooks/), [3](https://www.red-gate.com/simple-talk/databases/sql-server/bi-sql-server/sql-server-machine-learning-services-part-3-plotting-data-python/)

#### Implementation Notes

- Input: SQL result set as a pandas DataFrame, original question, and optional chart preference.
- Output: narrative insights, KPI values, and one or more chart artifacts.
- Preferred charting library for v1: Plotly, because it is already in the project dependencies.
- Chart generation should be deterministic where possible. For common shapes like time series, category counts, and comparisons, choose a chart type from explicit heuristics before asking the model to improvise.

#### Required Behaviors

- Detect whether the data supports a chart at all.
- Produce 2-5 concise observations tied directly to the data.
- Calculate a small KPI set when time-series or grouped data is present.
- Save artifacts to a predictable output directory such as `outputs/reports/<timestamp>/`.

#### Deliverables

- DataFrame profiling helper.
- Chart selection helper.
- Chart renderer for bar, line, and pie charts.
- KPI calculator for counts, percentages, and month-over-month growth.
- Tests for representative DataFrame-to-chart flows.

### 3. The Reporting Agent

- **Role:** Combines the analyst's insights and generated chart images into a clean, executive-ready presentation layout.
- **Tools:** File Export Tool (`markdown`, `pdfkit`, or `weasyprint`).
- **Output:** Returns a comprehensive report containing summarized takeaways, clear KPI callouts, and embedded visual charts.

#### Implementation Notes

- Input: original user question, SQL used, analyst observations, KPI summary, and chart file paths.
- Output: markdown report for v1, with optional PDF export later.
- The first deliverable should optimize for readability in GitHub and local editors.

#### Required Sections

- Title and timestamp
- Original business question
- Executive summary
- KPI section
- Charts section
- SQL appendix
- Caveats section when the data is incomplete or ambiguous

#### Deliverables

- Markdown report template.
- Artifact manifest describing generated files.
- Optional HTML-to-PDF export step after markdown output is stable.

## Recommended Technical Approach

Use a tool-based local architecture first.

- Agent orchestration: LangChain is acceptable because it is already in the dependency direction of the repo, but keep the domain and tool layers provider-agnostic.
- Model provider: Gemini API.
- Charting: Plotly first, with pandas-based preprocessing.
- Execution surface: CLI entrypoint via `askdata`.

LangGraph is not required for v1. Add it only if we need durable workflows, branching, retries, or human approval steps.

## Proposed Module Layout

Add the following modules under `src/askdata/`:

- `config.py`
	- environment parsing
	- paths for database and output directories
	- model configuration
- `db.py`
	- SQLite connection management
	- schema introspection
	- safe read-only query execution
- `schema_cache.py`
	- cached schema summary for prompts and validation
- `sql_guardrails.py`
	- SQL validation and normalization
- `models.py`
	- dataclasses or Pydantic models for agent outputs
- `tools.py`
	- tool wrappers for schema inspection, query execution, and report export
- `agents/data_engineer.py`
	- prompt and invocation logic for SQL generation
- `agents/bi_analyst.py`
	- insight generation and chart planning logic
- `agents/reporter.py`
	- markdown report assembly
- `charts.py`
	- chart generation helpers
- `kpis.py`
	- KPI computations
- `pipeline.py`
	- orchestration across the three agents
- `cli.py`
	- command-line parsing and user entrypoint

Update `src/askdata/__init__.py` so `main()` dispatches into the CLI instead of printing a placeholder message.

## Proposed Data Models

Define structured outputs to reduce prompt ambiguity:

- `UserRequest`
	- `question: str`
	- `preferred_chart: str | None`
- `SchemaSummary`
	- `tables: list[TableSummary]`
- `SqlPlan`
	- `sql: str`
	- `reasoning: str`
	- `expected_columns: list[str]`
- `QueryResult`
	- `sql: str`
	- `rows_returned: int`
	- `dataframe: pd.DataFrame`
- `AnalysisSummary`
	- `insights: list[str]`
	- `kpis: list[KPI]`
	- `recommended_charts: list[ChartSpec]`
- `ReportArtifacts`
	- `report_path: str`
	- `chart_paths: list[str]`

## End-to-End Flow

1. User runs a CLI command such as `uv run askdata "Show monthly order volume and summarize the trend"`.
2. The CLI loads config, checks for `data/orders.db`, and initializes the schema cache.
3. The Data Engineer Agent receives the user question and schema summary.
4. The generated SQL is validated by the guardrails layer.
5. The query executes against SQLite and returns a DataFrame.
6. The BI Analyst Agent inspects the DataFrame, computes KPIs, and generates charts.
7. The Reporting Agent writes a markdown report and stores artifacts in an output directory.
8. The CLI prints a concise summary and the generated report path.

## Tool Definitions

The initial tool surface should stay narrow:

- `get_schema_summary()`
	- returns known tables and columns
- `run_read_only_sql(sql: str)`
	- validates and executes safe SQL
