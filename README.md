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
provider.** The only real commands run so far were `claude --version`, `claude --help` and
`claude auth status` (local, no model request) while designing `claude_cli`.

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
| `claude_cli` provider (`claude -p`, text-only): request, scrubbed env, tools disabled | yes | yes | **no** (awaiting approval) |
| `claude_cli` preflight: login + eligibility check, limit / auth / timeout / malformed-output handling | yes | yes | **no** (awaiting approval) |
| Nebula adapter | **stub only** (always "not configured") | yes | no, API not verified |
| `ask`, `clean` commands | placeholders | exit code only | no |
| Data tools (files, SQL, pandas), agent runner, **tool execution** | **not built** | n/a | n/a |

## Billing: which provider costs what

| Provider | How it authenticates | What it bills |
|---|---|---|
| `anthropic` (this repo's adapter) | `ANTHROPIC_API_KEY` against the Anthropic API | **Metered API usage**, separate from a Claude Code subscription. |
| `claude_cli` | Your Claude Code login, via `claude -p` | **Subscription limits** (no API charge expected). See below. |
| `openai_compat` | Your server's key | Whatever that server charges. |
| `nebula` | none (stub) | nothing; makes no calls |

### Using your Claude Code subscription (`claude_cli`)

Per Anthropic's [help article](https://support.claude.com/en/articles/15036540), `claude -p`
signed in with a Claude plan draws from subscription limits. `claude_cli` is a small text-only
provider that runs exactly that, and nothing else:

```bash
claude auth login                       # once, with your Claude plan (not a Console API key)
echo "NEBULA_AGENT_ENABLE=claude_cli" >> .env
nebula-agent providers test claude_cli -m sonnet     # makes ONE small real request
```

```yaml
# agents.yaml
agents:
  qa:
    provider: claude_cli
    model: sonnet          # any model name/alias the claude CLI accepts
```

What it does before and during a request:

1. **Preflight, no model request.** `claude auth status --json` must report `loggedIn: true`,
   `apiProvider: firstParty` and an `authMethod` in the allowlist (`oauth_token`; `claude.ai` is
   expected but not yet observed). Anything else, including unknown values, is refused and nothing
   is sent. The CLI does not report your plan type, so this proves "a first-party subscription-style
   login", not which plan; it is a best-effort guard, not a billing guarantee.
2. **Scrubbed environment.** Every `ANTHROPIC_*` variable (API key, auth token, base URL, profile,
   federation) and `CLAUDE_CODE_USE_BEDROCK/VERTEX/FOUNDRY` is removed from the child process,
   for the preflight and the request alike. [Per the docs](https://code.claude.com/docs/en/authentication),
   in `-p` mode a present `ANTHROPIC_API_KEY` would otherwise always win over your subscription.
3. **Text only.** `--tools ""` disables every built-in Claude Code tool (so no commands, file edits or
   sub-agents), plus `--strict-mcp-config`, `--disable-slash-commands`, `--no-session-persistence`,
   `--setting-sources project`, run from an empty temp directory. Tools or tool results passed to
   it are rejected before anything runs. The prompt goes over stdin; argv is fixed, with no shell.
4. **Failures are explicit:** timeout, not logged in, ineligible login, usage limit reached
   (`ProviderLimitError`), non-zero exit and malformed output each raise a distinct error. The
   command then fails; it never retries on, or switches to, another provider.

Limits of this guard: a stored Console API key or an `apiKeyHelper` in *user* settings is not
visible in `auth status`; `--setting-sources project` keeps user settings out of the request, and
the auth-method allowlist rejects API-key logins, but only a real run can confirm the combination
behaves as intended on your machine. Terms and limits change, so re-check them.

### Paid providers are off by default

`anthropic`, `openai_compat` and `claude_cli` are disabled unless named in `NEBULA_AGENT_ENABLE`
(comma-separated, set in `.env`). Having a key in the environment is **not** enough.
Each agent uses exactly the provider named in `agents.yaml`. If it fails, the command fails:
there is no automatic switch to another provider, and `agents.yaml` rejects a `fallback:` key.

## Safety model

- **Model output is untrusted.** A parsed tool call is inert data; the provider layer rejects
  calls with no id, non-object arguments, or a tool name that was not offered in that request.
- **Tool results are untrusted data.** They are sent back to the model only as `tool_result` /
  `role: tool` messages, never merged into the system prompt (covered by a test).
- **Nothing executes tools today.** There is no tool-running code in this repo. The only process
  spawn is `claude_cli` running the fixed `claude` argv above (a scan finds no shell use, `eval`,
  `exec` or dynamic imports). `tools:` and `require_approval:` in
  `agents.yaml` are parsed but **not enforced anywhere yet**, because there is nothing to enforce.
  Before milestone 3 adds tools, the runner must implement: deny by default, run only tools in the
  agent's `tools` list, require explicit approval for `require_approval` tools, and read-only SQL
  unless `--apply`. See PLAN.md.
