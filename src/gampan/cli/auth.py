"""`gampan auth {login,logout,status}` subcommands."""

from __future__ import annotations

import typer

from gampan.gam.oauth import (
    browser_login,
    clear_credentials,
    device_code_login,
    load_credentials,
    store_credentials,
)

app = typer.Typer(help="Authentication commands.")


@app.command("login")
def login(
    device_code: bool = typer.Option(
        False, "--device-code", help="Use device-code flow (headless)."
    ),
) -> None:
    """Open browser, complete OAuth, store refresh token in OS keychain."""
    if device_code:
        email, refresh_token = device_code_login()
    else:
        email, refresh_token = browser_login()
    store_credentials(email=email, refresh_token=refresh_token)
    typer.echo(f"Logged in as {email}")


@app.command("logout")
def logout() -> None:
    """Clear stored credentials."""
    clear_credentials()
    typer.echo("Logged out.")


@app.command("status")
def status() -> None:
    """Show current principal + token presence."""
    creds = load_credentials()
    if not creds:
        typer.echo("Not logged in. Run `gampan auth login`.")
        raise typer.Exit(code=1)
    typer.echo(f"Logged in as {creds['email']}")
