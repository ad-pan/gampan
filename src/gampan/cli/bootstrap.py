"""`gampan bootstrap-test-network` — create or discover a Google Ad Manager network."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from ruamel.yaml import YAML

from gampan.gam.auth import resolve_credentials
from gampan.gam.clients.factory import soap_bootstrap_service_factory

_ALREADY_ASSOCIATED = "GOOGLE_ACCOUNT_ALREADY_ASSOCIATED_WITH_NETWORK"


def run(
    write_config: bool = typer.Option(
        True,
        "--write-config/--no-write-config",
        help="Write the resolved network_code to .gampan/config.yml (default: yes)",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite existing network_code in config.yml without prompting",
    ),
) -> None:
    """Create a GAM test network, or — if the account is already on a network — list
    existing networks so the user can point gampan at one of them.
    """
    creds = resolve_credentials()
    service = soap_bootstrap_service_factory(creds)

    try:
        network = service.makeTestNetwork()
        code, display_name = _extract_network(network)
        typer.echo("✓ Test network created.")
    except Exception as e:
        if _ALREADY_ASSOCIATED not in str(e):
            raise
        networks = _list_existing(service)
        if not networks:
            typer.echo(
                "Google account is associated with a network but `getAllNetworks` returned\n"
                "nothing — that should not happen. Check your account's GAM access.",
                err=True,
            )
            raise typer.Exit(code=1) from e
        if len(networks) == 1:
            code, display_name = networks[0]
            typer.echo("ℹ Your Google account is already associated with this network:")
        else:
            typer.echo("ℹ Your Google account is associated with multiple networks:")
            for c, n in networks:
                typer.echo(f"  - {c}  {n}")
            typer.echo(
                "\nNo single network to auto-select. Re-run `gampan init --network-code <code>`\n"
                "with the one you want gampan to manage."
            )
            raise typer.Exit(code=0) from e

    typer.echo(f"  Network code:  {code}")
    typer.echo(f"  Display name:  {display_name}")
    typer.echo(f"  UI:            https://admanager.google.com/{code}")

    if not write_config:
        return

    _maybe_write_config(code, force)


def _extract_network(network: Any) -> tuple[str, str]:
    """Pull (networkCode, displayName) from a zeep SOAP Network object."""
    code = str(network["networkCode"])
    display_name = str(network["displayName"]) if "displayName" in network else "(unnamed)"
    return code, display_name


def _list_existing(service: Any) -> list[tuple[str, str]]:
    """Return list of (network_code, display_name) for every network the account sees."""
    result = service.getAllNetworks()
    return [_extract_network(n) for n in result]


def _maybe_write_config(code: str, force: bool) -> None:
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
