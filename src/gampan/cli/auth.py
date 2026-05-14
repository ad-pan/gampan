"""`gampan auth {login,logout,status}` subcommands."""

from __future__ import annotations

import sys

import typer

from gampan.gam import credential_store
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
    """Open browser, complete OAuth, store refresh token in credential file."""
    if device_code:
        email, refresh_token = device_code_login()
    else:
        email, refresh_token = browser_login()
    store_credentials(email=email, refresh_token=refresh_token)
    cred_path = credential_store._file_path()
    typer.echo(f"Logged in as {email}")
    typer.echo(f"  Credentials stored at: {cred_path}")
    if sys.platform == "darwin":
        typer.echo(
            "  (Previous gampan versions stored these in macOS Keychain;\n"
            "   you can clear that stale entry with:"
            " security delete-generic-password -s gampan)"
        )


@app.command("logout")
def logout() -> None:
    """Clear stored credentials."""
    cred_path = credential_store._file_path()
    clear_credentials()
    typer.echo(f"Logged out (cleared {cred_path})")


@app.command("status")
def status() -> None:
    """Show current principal + token presence."""
    creds = load_credentials()
    if not creds:
        typer.echo("Not logged in. Run `gampan auth login`.")
        raise typer.Exit(code=1)
    typer.echo(f"Logged in as {creds['email']}")
