import socket

import pytest

SECRET_ENV = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "OPENAI_COMPAT_API_KEY",
    "OPENAI_COMPAT_BASE_URL",
    "NEBULA_API_KEY",
    "NEBULA_BASE_URL",
    "NEBULA_AGENT_ENABLE",
)


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    """No real credentials, no .env loading, no network: tests can never reach a paid API."""
    for var in SECRET_ENV:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("nebula_agent.cli.load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr("nebula_agent.config.load_dotenv", lambda *a, **k: None)

    def blocked(self, *a, **k):
        raise RuntimeError("network access is blocked in tests")

    monkeypatch.setattr(socket.socket, "connect", blocked)


@pytest.fixture(autouse=True)
def no_real_subprocess(monkeypatch):
    """Tests must never launch the real `claude` CLI; they inject a fake runner instead."""

    def blocked(*a, **k):
        raise RuntimeError("subprocess is blocked in tests; inject a fake runner")

    monkeypatch.setattr("nebula_agent.providers.claude_cli.subprocess.run", blocked)
