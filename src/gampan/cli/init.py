"""`gampan init` — scaffold a new repo."""

from __future__ import annotations

from pathlib import Path

import typer
from ruamel.yaml import YAML


def run(
    network_code: str = typer.Option(..., "--network-code", "-n", prompt="GAM network code"),
    env: str = typer.Option("default", "--env", "-e"),
    non_interactive: bool = typer.Option(False, "--non-interactive"),
) -> None:
    """Create `.gampan/config.yml` and resource directories."""
    root = Path.cwd()
    cfg_dir = root / ".gampan"
    cfg_dir.mkdir(exist_ok=True)
    cfg_file = cfg_dir / "config.yml"
    if cfg_file.exists():
        typer.echo(f"refusing to overwrite existing {cfg_file}")
        raise typer.Exit(code=1)

    yaml = YAML()
    with cfg_file.open("w") as f:
        yaml.dump(
            {"network_code": network_code, "env": env, "default_dry_run": False},
            f,
        )

    for d in ("native-styles", "creative-templates", "native-formats"):
        (root / d).mkdir(exist_ok=True)

    typer.echo(f"initialized {cfg_file}")
    typer.echo("  native-styles/ ready")
    typer.echo("  creative-templates/ ready")
    typer.echo("  native-formats/ ready")
    if not non_interactive:
        typer.echo("\nNext: `gampan auth login`, then `gampan import`.")
