from typer.testing import CliRunner

from nebula_agent.cli import app

runner = CliRunner()


def test_version():
    assert runner.invoke(app, ["version"]).stdout.strip() == "0.1.0"


def test_agents_lists_configured():
    result = runner.invoke(app, ["agents"])
    assert result.exit_code == 0
    assert "qa: anthropic/" in result.stdout


def test_providers_includes_nebula():
    assert "nebula" in runner.invoke(app, ["providers", "list"]).stdout


def test_ask_placeholder_exits_nonzero():
    assert runner.invoke(app, ["ask", "hi"]).exit_code == 2
