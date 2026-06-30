# Work Items Remaining

## Setup
- [ ] Add module stubs under `src/askdata/`: `config.py`, `db.py`, `schema_cache.py`, `sql_guardrails.py`, `models.py`, `tools.py`, `charts.py`, `kpis.py`, `pipeline.py`, `cli.py`
- [ ] Define Pydantic/dataclass models: `UserRequest`, `SchemaSummary`, `SqlPlan`, `QueryResult`, `AnalysisSummary`, `ReportArtifacts`
- [ ] Update `__init__.py` to dispatch `main()` to CLI

## Data Engineer Agent (`agents/data_engineer.py`)
- [ ] Build schema cache from SQLite metadata
- [ ] Implement SQL guardrails (SELECT/WITH only; block writes, DDL, multi-statement, PRAGMA)
- [ ] Enforce row limit injection when absent
- [ ] Validate table/column names against cached schema before execution
- [ ] Write prompt template for SQL generation (input: question + schema; output: `SqlPlan`)
- [ ] Unit tests for allowed and blocked SQL patterns

## BI Analyst Agent (`agents/bi_analyst.py`)
- [ ] DataFrame profiling helper (shape, types, nulls)
- [ ] Chart selection heuristics (time series → line, categorical → bar, part-of-whole → pie)
- [ ] Chart renderer for bar, line, and pie via Plotly
- [ ] KPI calculator (counts, percentages, month-over-month growth)
- [ ] Observation generator (2–5 data-grounded insights)
- [ ] Tests for representative DataFrame → chart flows

## Reporting Agent (`agents/reporter.py`)
- [ ] Markdown report template (title, timestamp, question, executive summary, KPIs, charts, SQL appendix, caveats)
- [ ] Artifact manifest for generated files
- [ ] Save outputs to `outputs/reports/<timestamp>/`

## Pipeline & CLI
- [ ] Orchestration in `pipeline.py` wiring all three agents end-to-end
- [ ] `get_schema_summary()` and `run_read_only_sql()` tool wrappers in `tools.py`
- [ ] CLI entrypoint (`askdata "<question>"`) with config load, DB check, and schema cache init

## V2 (Backlog)
- [ ] LLM-as-judge to score generated SQL
- [ ] Swap model provider to local Ollama models
