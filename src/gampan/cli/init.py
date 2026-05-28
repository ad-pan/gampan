"""`gampan init` — scaffold a new repo."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from ruamel.yaml import YAML


def run(
    network_code: str = typer.Option(..., "--network-code", "-n", prompt="GAM network code"),
    envs: str | None = typer.Option(
        None,
        "--envs",
        help=(
            "Comma-separated environments to declare (e.g. `dev,prod`). Omit "
            "for a single-environment (v1) repo. When set, scaffolds an "
            "`environments:` block; author `.gampan/hooks` to map each env to "
            "your GAM naming convention."
        ),
    ),
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

    # ``include_archived``: ARCHIVED resources are filtered out of
    # ``import`` / ``plan`` by default — flip to ``true`` (or pass
    # ``--include-archived``) when a NativeStyle YAML carries ``status: ARCHIVED``.
    config: dict[str, Any] = {
        "network_code": network_code,
        "default_dry_run": False,
        "include_archived": False,
    }

    env_names: list[str] = []
    if envs is not None:
        env_names = [e.strip() for e in envs.split(",")]
        if any(not name for name in env_names):
            typer.echo(
                "Error: --envs contains an empty/blank environment name "
                f"(got {envs!r}). Use a clean comma-separated list, e.g. `dev,prod`.",
                err=True,
            )
            raise typer.Exit(code=2)
        # Declare each env with an empty body; per-env `vars` and the hook
        # mapping are authored afterwards.
        config["environments"] = {name: {} for name in env_names}

    yaml = YAML()
    with cfg_file.open("w") as f:
        yaml.dump(config, f)

    for d in ("native-styles", "creative-templates", "native-formats"):
        (root / d).mkdir(exist_ok=True)

    typer.echo(f"initialized {cfg_file}")
    typer.echo("  native-styles/ ready")
    typer.echo("  creative-templates/ ready")
    typer.echo("  native-formats/ ready")
    if env_names:
        typer.echo(f"  environments: {', '.join(env_names)}")
    if not non_interactive:
        if env_names:
            typer.echo(
                "\nNext: `gampan auth login`, author `.gampan/hooks` for your "
                "env naming convention (see examples/multi-env), then "
                "`gampan import` (imports all declared environments)."
            )
        else:
            typer.echo("\nNext: `gampan auth login`, then `gampan import`.")
