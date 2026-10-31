from __future__ import annotations

from pathlib import Path

import typer

from nebula_agent import __version__
from nebula_agent.config import DEFAULT_CONFIG, KNOWN_PROVIDERS, load_config

app = typer.Typer(help="AI agents for data analytics and cleaning.", no_args_is_help=True)

ConfigOpt = typer.Option(DEFAULT_CONFIG, "--config", "-c", help="Path to agents.yaml")


@app.command()
def version() -> None:
    """Print the version."""
    typer.echo(__version__)


@app.command()
def agents(config: Path = ConfigOpt) -> None:
    """List configured agents."""
    try:
        cfg = load_config(config)
    except (FileNotFoundError, ValueError) as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from e
    for name, agent in cfg.agents.items():
        typer.echo(f"{name}: {agent.provider}/{agent.model} (max_steps={agent.max_steps})")


@app.command()
def providers() -> None:
    """List known model providers."""
    for name in KNOWN_PROVIDERS:
        typer.echo(name)


@app.command()
def ask(question: str) -> None:
    """Ask a question about your data (not implemented yet)."""
    typer.secho("ask is not implemented yet (milestone 5).", fg=typer.colors.YELLOW, err=True)
    raise typer.Exit(2)


@app.command()
def clean(path: Path) -> None:
    """Clean a dataset (not implemented yet)."""
    typer.secho("clean is not implemented yet (milestone 6).", fg=typer.colors.YELLOW, err=True)
    raise typer.Exit(2)
