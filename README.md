# nebula-agent

CLI for AI agents that automate data analytics and cleaning. See [PLAN.md](PLAN.md).

```bash
pip install -e ".[dev]"
cp .env.example .env
nebula-agent agents          # list configured agents
nebula-agent providers       # list known providers
pytest && ruff check .
```

Status: milestone 1 (scaffold). `ask` and `clean` are placeholders.
