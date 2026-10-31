import pytest
from typer.testing import CliRunner

import nebula_agent.cli as cli
from nebula_agent.config import load_config
from nebula_agent.providers import (
    NotConfiguredError,
    ProviderDisabledError,
    ProviderError,
    get_provider,
)
from nebula_agent.providers.anthropic import AnthropicProvider
from nebula_agent.providers.openai_compat import OpenAICompatProvider

runner = CliRunner()


@pytest.mark.parametrize("name", ["anthropic", "openai_compat"])
def test_paid_providers_disabled_by_default_even_with_credentials(monkeypatch, name):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    monkeypatch.setenv("OPENAI_COMPAT_BASE_URL", "http://x/v1")
    with pytest.raises(ProviderDisabledError, match="NEBULA_AGENT_ENABLE"):
        get_provider(name)


def test_enabling_without_credentials_is_not_configured(monkeypatch):
    monkeypatch.setenv("NEBULA_AGENT_ENABLE", "anthropic")
    with pytest.raises(NotConfiguredError) as e:
        get_provider("anthropic")
    assert not isinstance(e.value, ProviderDisabledError)


def test_enabling_one_does_not_enable_the_other(monkeypatch):
    monkeypatch.setenv("NEBULA_AGENT_ENABLE", " Anthropic ")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    monkeypatch.setenv("OPENAI_COMPAT_BASE_URL", "http://x/v1")
    assert isinstance(get_provider("anthropic"), AnthropicProvider)
    with pytest.raises(ProviderDisabledError):
        get_provider("openai_compat")


def test_openai_compat_builds_when_enabled(monkeypatch):
    monkeypatch.setenv("NEBULA_AGENT_ENABLE", "openai_compat")
    monkeypatch.setenv("OPENAI_COMPAT_BASE_URL", "http://x/v1")
    assert isinstance(get_provider("openai_compat"), OpenAICompatProvider)


def test_cli_reports_disabled_with_exit_3():
    result = runner.invoke(cli.app, ["providers", "test", "anthropic", "-m", "m"])
    assert result.exit_code == 3 and "disabled" in result.output


def test_cli_list_shows_state(monkeypatch):
    monkeypatch.setenv("NEBULA_AGENT_ENABLE", "anthropic")
    out = runner.invoke(cli.app, ["providers", "list"]).stdout
    assert "anthropic: enabled" in out
    assert "openai_compat: disabled" in out
    assert "nebula: stub (not configured)" in out


def test_no_automatic_fallback_when_selected_provider_fails(monkeypatch):
    built = []

    def fake_get_provider(name):
        built.append(name)
        raise ProviderError("simulated outage")

    monkeypatch.setattr(cli, "get_provider", fake_get_provider)
    monkeypatch.setenv("NEBULA_AGENT_ENABLE", "anthropic,openai_compat")
    result = runner.invoke(cli.app, ["providers", "test", "anthropic", "-m", "m"])
    assert result.exit_code == 1
    assert built == ["anthropic"]  # no other provider was ever constructed


def test_config_rejects_fallback_setting(tmp_path):
    p = tmp_path / "agents.yaml"
    p.write_text("agents:\n  qa:\n    provider: nebula\n    model: m\n    fallback: anthropic\n")
    with pytest.raises(ValueError, match="fallback"):
        load_config(p)
