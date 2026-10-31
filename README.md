# nebula-agent

CLI for AI agents that automate data analytics and cleaning. See [PLAN.md](PLAN.md) for the roadmap.

```bash
pip install -e ".[dev]"
cp .env.example .env                   # then edit; .env is gitignored
nebula-agent agents                    # list configured agents
nebula-agent providers list            # show which providers are enabled
pytest && ruff check .
```

## Status

"Mock-tested" means automated tests with fake clients; the test suite blocks all network access
and strips credentials, so it cannot reach a paid API. **Nothing has been tested against a real
provider** (no credentials have been used in this project so far).

| Area | Implemented | Mock-tested | Tested against a real provider |
|---|---|---|---|
| Config loading / validation (`agents.yaml`, unknown keys rejected) | yes | yes | n/a |
| CLI: `version`, `agents`, `providers list`, `providers test` | yes | yes | no |
| Anthropic adapter: text, tool calls, tool results | yes | yes | **no** |
| Anthropic adapter: malformed responses, auth failure (401/403), server/network errors | yes | yes | **no** |
| OpenAI-compatible adapter: same cases as above | yes | yes | **no** |
| Opt-in gating for paid providers | yes | yes | n/a |
| No automatic fallback between providers | yes (nothing falls back) | yes | n/a |
| Rejecting tool calls the model was not offered | yes | yes | no |
| Nebula adapter | **stub only** (always "not configured") | yes | no, API not verified |
| `ask`, `clean` commands | placeholders | exit code only | no |
| Data tools (files, SQL, pandas), agent runner, **tool execution** | **not built** | n/a | n/a |

## Billing: which provider costs what

| Provider | How it authenticates | What it bills |
|---|---|---|
| `anthropic` (this repo's adapter) | `ANTHROPIC_API_KEY` against the Anthropic API | **Metered API usage**, separate from a Claude Code subscription. |
| `openai_compat` | Your server's key | Whatever that server charges. |
| `nebula` | none (stub) | nothing; makes no calls |

Using your Claude Code subscription: per Anthropic's [help article](https://support.claude.com/en/articles/15036540),
`claude -p` and the Agent SDK signed in with a Claude plan draw from subscription limits, so the
supported route would be driving the `claude` CLI, not calling the API from this adapter.
That route is **not built** here. Two cautions from the [Claude Code docs](https://code.claude.com/docs/en/authentication):
in `claude -p` mode an `ANTHROPIC_API_KEY` in the environment is always used when present
(moving usage to API billing), and monthly API credits on Max/Ultra/Team apply only to API-key
usage through a linked Console organization. Terms change, so re-check before relying on this.

### Paid providers are off by default

`anthropic` and `openai_compat` are disabled unless named in `NEBULA_AGENT_ENABLE`
(comma-separated, set in `.env`). Having a key in the environment is **not** enough.
Each agent uses exactly the provider named in `agents.yaml`. If it fails, the command fails:
there is no automatic switch to another provider, and `agents.yaml` rejects a `fallback:` key.

## Safety model

- **Model output is untrusted.** A parsed tool call is inert data; the provider layer rejects
  calls with no id, non-object arguments, or a tool name that was not offered in that request.
- **Tool results are untrusted data.** They are sent back to the model only as `tool_result` /
  `role: tool` messages, never merged into the system prompt (covered by a test).
- **Nothing executes tools today.** There is no tool-running code in this repo (a scan finds no
  `subprocess`, `eval`, `exec` or dynamic imports). `tools:` and `require_approval:` in
  `agents.yaml` are parsed but **not enforced anywhere yet**, because there is nothing to enforce.
  Before milestone 3 adds tools, the runner must implement: deny by default, run only tools in the
  agent's `tools` list, require explicit approval for `require_approval` tools, and read-only SQL
  unless `--apply`. See PLAN.md.
