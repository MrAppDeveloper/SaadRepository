# nebula-agent

CLI for AI agents that automate data analytics and cleaning. See [PLAN.md](PLAN.md).

```bash
pip install -e ".[dev]"
cp .env.example .env
nebula-agent agents          # list configured agents
nebula-agent providers list  # list known providers
nebula-agent providers test anthropic -m claude-sonnet-5-5  # connectivity check
pytest && ruff check .
```

Status: milestone 2 (provider layer). `ask` and `clean` are placeholders.
