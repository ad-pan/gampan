"""`gampan auth ...` — subcommands implemented in Task 23."""

import typer

app = typer.Typer(help="Authentication commands.")


@app.command("login")
def login() -> None:
    typer.echo("auth login: not yet implemented")
    raise typer.Exit(code=1)


@app.command("logout")
def logout() -> None:
    typer.echo("auth logout: not yet implemented")
    raise typer.Exit(code=1)


@app.command("status")
def status() -> None:
    typer.echo("auth status: not yet implemented")
    raise typer.Exit(code=1)
