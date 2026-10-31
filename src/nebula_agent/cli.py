from __future__ import annotations

from pathlib import Path

import typer
from dotenv import load_dotenv

from nebula_agent import __version__
from nebula_agent.config import DEFAULT_CONFIG, KNOWN_PROVIDERS, load_config
from nebula_agent.providers import Message, NotConfiguredError, ProviderError, get_provider

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


providers_app = typer.Typer(help="Inspect and test model providers.", no_args_is_help=True)
app.add_typer(providers_app, name="providers")


@providers_app.command("list")
def providers_list() -> None:
    """List known model providers."""
    for name in KNOWN_PROVIDERS:
        typer.echo(name)


@providers_app.command("test")
def providers_test(
    name: str = typer.Argument(..., help="Provider name"),
    model: str = typer.Option(..., "--model", "-m", help="Model id to call"),
) -> None:
    """Send a tiny request to confirm the provider is configured and reachable."""
    load_dotenv()
    try:
        provider = get_provider(name)
        reply = provider.chat(model, [Message(role="user", content="Reply with the word OK.")])
    except ValueError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from e
    except NotConfiguredError as e:
        typer.secho(f"Not configured: {e}", fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(3) from e
    except ProviderError as e:
        typer.secho(f"Failed: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from e
    typer.echo(f"{name}/{model}: {reply.text.strip()[:80]}")


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
