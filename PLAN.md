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
| Nebula access | **API not verified.** No endpoint is assumed. Ship a Nebula adapter stub that raises "not configured" until real docs/credentials are confirmed |
| Agent runtime (initially) | Local Claude agents (Anthropic API), run by our own tool-use loop |
| Nebula usage (later) | Call existing Nebula-hosted agents, once the API is verified |
| Second SQL database | PostgreSQL (after SQLite) |
| Outputs | Local files first. Database writes come later, behind explicit approval |

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
    provider: anthropic        # switch to nebula once the API is verified
    model: claude-sonnet-5-5
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

Hard requirements for milestones 3-4 (nothing below is enforced yet because no tool executes):

- **Deny by default.** The runner executes only tools listed in the agent's `tools`, and only after validating arguments against the tool's schema.
- **Approval gate.** Tools in `require_approval` never run without an explicit human confirmation.
- **Untrusted inputs.** Model output, file contents, SQL results and API responses are data, never instructions. Tool results go back to the model only as tool-result messages.
- **Providers are opt-in and never swapped.** Paid providers need `NEBULA_AGENT_ENABLE`; a failing provider fails the run instead of falling back to another.

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

## Resolved

- **Usage mode**: local Claude agents first; existing Nebula-hosted agents are integrated later.
- **SQL**: SQLite first, then PostgreSQL.
- **Outputs**: local files first. Database writes are added later and always require approval (`--apply` plus confirmation).

## Still open (blocks milestone 7 only)

1. **Nebula API**: not verified. Before building the adapter we need the official docs URL, base URL, auth scheme, and how hosted agents are listed and invoked. Until then no endpoint is assumed and the adapter stays a stub. (An unconfirmed lead: the npm package `@thirdweb-dev/nebula`, which may or may not be the same product.)

Milestones 1-6 do not depend on this, so they can start immediately.
