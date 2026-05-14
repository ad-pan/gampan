"""Typer application root."""

from __future__ import annotations

import typer

from gampan import __version__
from gampan.cli import (
    apply as apply_cmd,
)
from gampan.cli import (
    auth as auth_cmd,
)
from gampan.cli import (
    bootstrap as bootstrap_cmd,
)
from gampan.cli import (
    import_cmd,
)
from gampan.cli import (
    info as info_cmd,
)
from gampan.cli import (
    init as init_cmd,
)
from gampan.cli import (
    plan as plan_cmd,
)
from gampan.cli import (
    refresh as refresh_cmd,
)
from gampan.cli.logging import configure as configure_logging

app = typer.Typer(
    name="gampan",
    help="Declarative IaC CLI for Google Ad Manager.",
    no_args_is_help=True,
)
app.add_typer(auth_cmd.app, name="auth", help="Authentication commands.")
app.command(name="init")(init_cmd.run)
app.command(name="bootstrap-test-network")(bootstrap_cmd.run)
app.command(name="import")(import_cmd.run)
app.command(name="plan")(plan_cmd.run)
app.command(name="apply")(apply_cmd.run)
app.command(name="refresh")(refresh_cmd.run)
app.command(name="info")(info_cmd.run)


@app.command()
def version() -> None:
    """Print version + build info."""
    typer.echo(f"gampan {__version__}")


@app.callback()
def main(
    verbose: int = typer.Option(0, "-v", count=True, help="Increase log verbosity (-v, -vv)."),
    json_logs: bool = typer.Option(False, "--log-format-json", help="Emit structured JSON logs."),
) -> None:
    configure_logging(verbosity=verbose, json_output=json_logs)
