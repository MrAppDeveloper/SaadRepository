# Plan: Nebula + Claude Code AI Agents for Data Analytics & Automation

## Goal

A Python CLI (`nebula-agent`) that runs AI agents over your data. The first two agents:

1. **Ask-your-data Q&A**: ask a question in plain English about a CSV/Excel file or a SQL database, and get back an answer, the query that produced it, and an optional chart.
2. **Data cleaning / ETL**: profile a dataset, propose cleaning steps, apply them after you approve, and write the result to a file or a table.

Claude Code is the development cockpit: it builds, runs, and debugs the CLI. The agents call LLMs through a **pluggable provider layer**, and each agent picks its provider and model in config. Nebula.gg is one provider; Claude (Anthropic API) is the working default until the Nebula API details are confirmed.

## Decisions so far

| Topic | Decision |
|---|---|
| Language | Python 3.11+ |
| Interface | CLI only for now (Typer). An MCP server can be added later on the same core. |
| Data sources (v1) | CSV / Excel, SQL (SQLite first, then Postgres/MySQL via SQLAlchemy) |
| Agents (v1) | Ask-your-data Q&A, Data cleaning/ETL |
| Model provider | Configurable per agent (YAML) |
| Nebula access | **Unknown, still open.** Ship a Nebula adapter stub and fill it in once the API is confirmed |

## Architecture

```
nebula-agent (Typer CLI)
        │
        ▼
  Agent runner ── tool-use loop (LLM ⇄ tools) with step limit + approvals
        │
   ┌────┴─────────────┐
   ▼                  ▼
Providers          Tools
 - anthropic        - list_tables / describe_schema
 - nebula (stub)    - run_sql (read-only by default)
 - openai-compat    - load_file (CSV/XLSX → DataFrame)
                    - run_pandas (sandboxed expression eval)
                    - profile_data
                    - write_output (requires --apply / confirmation)
        │
        ▼
 Data connectors: pandas (CSV/XLSX), SQLAlchemy (SQLite/Postgres/MySQL)
```

### Proposed layout

```
src/nebula_agent/
  cli.py                 # Typer entrypoint: ask, clean, agents, providers
  config.py              # loads agents.yaml + .env
  runner.py              # generic tool-use loop
  providers/
    base.py              # Provider protocol: chat(messages, tools) -> response
    anthropic.py
    nebula.py            # stub → real once API confirmed
    openai_compat.py     # generic /v1/chat/completions (Nebula may fit here)
  tools/
    sql.py  files.py  pandas_exec.py  profiling.py  output.py
  agents/
    qa.py  cleaner.py    # system prompts + allowed tool sets
agents.yaml              # per-agent provider/model/tools
.env.example             # ANTHROPIC_API_KEY, NEBULA_API_KEY, NEBULA_BASE_URL
tests/
  fixtures/ (sample.csv, sample.sqlite)
```

### Example `agents.yaml`

```yaml
agents:
  qa:
    provider: anthropic        # or: nebula, openai_compat
    model: claude-sonnet-5-5
    tools: [list_tables, describe_schema, run_sql, load_file, run_pandas]
    max_steps: 12
  cleaner:
    provider: nebula
    model: <nebula-model-id>
    tools: [load_file, profile_data, run_pandas, write_output]
    require_approval: [write_output]
```

### Example CLI usage

```bash
nebula-agent ask "Top 5 customers by revenue last quarter" --db sqlite:///sales.db
nebula-agent ask "Which month had the most refunds?" --file orders.xlsx --chart out.png
nebula-agent clean customers.csv --out customers_clean.csv          # dry run: shows the plan
nebula-agent clean customers.csv --out customers_clean.csv --apply  # executes the plan
nebula-agent providers test nebula                                  # connectivity check
```

## Safety guardrails

- SQL runs read-only by default (`SELECT` only, with a row limit). Writes need `--apply`.
- Pandas code runs in a restricted evaluator (no imports, file or network access), with a timeout.
- The cleaner always shows a dry-run diff and plan before it writes anything.
- Secrets live only in `.env`, which is gitignored. Only `.env.example` is committed.
- Every run writes a transcript (prompts, tool calls, results) to `runs/` for audit and debugging.

## Milestones

1. **Scaffold**: `pyproject.toml`, package layout, Typer CLI skeleton, config loading, `.env.example`, lint/test setup (ruff, pytest).
2. **Provider layer**: `Provider` protocol, Anthropic adapter, OpenAI-compatible adapter, Nebula stub, `providers test` command.
3. **Data tools**: file loading, schema introspection, read-only SQL, sandboxed pandas, profiling, with unit tests on fixtures.
4. **Runner**: tool-use loop with step limits, approvals, and transcript logging.
5. **Q&A agent**: `nebula-agent ask`, end-to-end on the sample CSV and SQLite data, plus an optional chart (matplotlib).
6. **Cleaner agent**: `nebula-agent clean`: profile, plan, dry-run diff, apply.
7. **Nebula integration**: implement the real adapter once the API is confirmed (see open questions).
8. **Later**: MCP server over the same core, Postgres/MySQL, scheduled runs.

## Open questions (needed before milestone 7)

1. **Nebula API**: Is there a public REST API for nebula.gg? What are the base URL and auth scheme? Is it OpenAI-compatible? (I found an npm package, `@thirdweb-dev/nebula`, with `getModels()`/`getAgents()` and secret-key auth. Is that the same product?)
2. **Nebula usage mode**: Should we call raw **models** for reasoning, or invoke **Nebula-hosted agents** (with their Gmail/Slack/GitHub integrations) as tools?
3. Which SQL database comes after SQLite: Postgres or MySQL?
4. Where should outputs go: local files only, or written back to the database?
