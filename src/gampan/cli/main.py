"""Typer application root."""

import typer

from gampan import __version__

app = typer.Typer(
    name="gampan",
    help="Declarative IaC CLI for Google Ad Manager.",
    no_args_is_help=True,
)


@app.callback()
def callback() -> None:
    """Declarative IaC CLI for Google Ad Manager."""


@app.command()
def version() -> None:
    """Print version + build info."""
    typer.echo(f"gampan {__version__}")
