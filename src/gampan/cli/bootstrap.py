"""`gampan bootstrap-test-network` — create a Google Ad Manager API test network."""

from __future__ import annotations

from pathlib import Path

import typer
from ruamel.yaml import YAML

from gampan.gam.auth import resolve_credentials
from gampan.gam.clients.factory import soap_bootstrap_service_factory


def run(
    write_config: bool = typer.Option(
        True,
        "--write-config/--no-write-config",
        help="Write the new network_code to .gampan/config.yml (default: yes)",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite existing network_code in config.yml without prompting",
    ),
) -> None:
    """Create a Google Ad Manager test network and (optionally) persist the code."""
    creds = resolve_credentials()
    service = soap_bootstrap_service_factory(creds)
    network = service.makeTestNetwork()
    # googleads/zeep SOAP responses support `__getitem__` and `in` but NOT `.get()`.
    code = str(network["networkCode"])
    display_name = str(network["displayName"]) if "displayName" in network else "(unnamed)"

    typer.echo("✓ Test network created.")
    typer.echo(f"  Network code:  {code}")
    typer.echo(f"  Display name:  {display_name}")
    typer.echo(f"  UI:            https://admanager.google.com/{code}")

    if not write_config:
        return

    cfg_path = Path.cwd() / ".gampan" / "config.yml"
    if not cfg_path.exists():
        typer.echo(
            f"\nNo .gampan/config.yml yet. Run `gampan init --network-code {code}` to scaffold."
        )
        return

    yaml = YAML()
    cfg = dict(yaml.load(cfg_path.read_text()))
    existing = cfg.get("network_code")
    if existing and existing != code and not force:
        msg = (
            f"\n.gampan/config.yml has network_code={existing!r}. Overwrite with {code!r}? (yes/no)"
        )
        confirm = typer.prompt(msg, default="no")
        if confirm.strip().lower() not in {"yes", "y"}:
            typer.echo("Leaving config.yml unchanged.")
            return

    cfg["network_code"] = code
    with cfg_path.open("w") as f:
        yaml.dump(cfg, f)
    typer.echo("\n.gampan/config.yml updated.")
