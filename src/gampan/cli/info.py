"""`gampan info` — diagnostic dump."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from ruamel.yaml import YAML

from gampan import __version__


def run(
    offline: bool = typer.Option(False, "--offline", help="Skip the GAM network call."),
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Print version + auth + network + config + state diagnostics."""
    root = Path.cwd()
    cfg_path = root / ".gampan" / "config.yml"
    config: dict[str, str] = {}
    if cfg_path.exists():
        yaml = YAML(typ="safe")
        config = dict(yaml.load(cfg_path.read_text()) or {})

    cfg_section: dict[str, str | None] = {
        "path": str(cfg_path.relative_to(root)) if cfg_path.exists() else None,
        "network_code": config.get("network_code"),
        "env": config.get("env"),
    }
    auth_section: dict[str, str] | None = None if offline else _gather_auth()
    network_code = config.get("network_code")
    network_section: dict[str, str] | None = None if offline else _probe_network(network_code)

    payload: dict[str, object] = {
        "version": __version__,
        "config": cfg_section,
        "auth": auth_section,
        "network": network_section,
    }

    if as_json:
        typer.echo(json.dumps(payload, indent=2))
        return

    typer.echo(f"gampan {__version__}\n")
    typer.echo("Config")
    typer.echo(f"  Config file:      {cfg_section['path']}")
    typer.echo(f"  Network code:     {cfg_section['network_code']}")
    typer.echo(f"  Env:              {cfg_section['env']}\n")
    if auth_section:
        typer.echo("Auth")
        for k, v in auth_section.items():
            typer.echo(f"  {k:18s}{v}")


def _gather_auth() -> dict[str, str]:
    from gampan.gam.auth import resolve_credentials

    try:
        creds = resolve_credentials()
        return {"Method:": "resolved", "Principal:": creds.principal}
    except Exception as e:
        return {"Status:": f"error — {e}"}


def _probe_network(network_code: str | None) -> dict[str, str] | None:
    # v0.1: omit a real probe; surface stub. Implementation extended in v0.1.1.
    if not network_code:
        return None
    return {"Network code:": network_code, "Connected:": "skipped (probe lands in v0.1.1)"}
