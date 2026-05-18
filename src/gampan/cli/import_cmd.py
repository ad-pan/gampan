"""`gampan import` — pull remote resources into local YAML + state."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import typer
from ruamel.yaml import YAML

from gampan.cli.plan import build_clients
from gampan.core.fs.writer import write_resource
from gampan.core.state.schema import ResourceEntry
from gampan.core.state.store import StateStore


def run(
    resource: str = typer.Option(
        "all", "--resource", "-r", help="native-styles | creative-templates | all"
    ),
) -> None:
    """Pull GAM resources into YAML + populate state.json."""
    root = Path.cwd()
    cfg_path = root / ".gampan" / "config.yml"
    if not cfg_path.exists():
        typer.echo("Not a gampan repo (missing .gampan/config.yml). Run `gampan init` first.")
        raise typer.Exit(code=1)
    yaml = YAML(typ="safe")
    cfg = dict(yaml.load(cfg_path.read_text()))

    clients = build_clients(cfg["network_code"])

    store = StateStore(root / ".gampan" / "state.json")
    state = store.load_or_empty(network_code=cfg["network_code"])

    kinds = _resolve_kinds(resource)
    # Track seen filename stems per-run to disambiguate slug collisions.
    seen_slugs: set[str] = set()
    # Track any stems that were disambiguated so we can report them.
    disambiguated: list[tuple[str, str]] = []  # (original_slug, final_stem)

    for kind in kinds:
        for gam_id, r in clients[kind].list():
            from gampan.core.fs.writer import slugify as _slugify

            slug_before = _slugify(r.name)
            yaml_path, stem = write_resource(root, r, gam_id=gam_id, seen_slugs=seen_slugs)
            if slug_before and stem != slug_before:
                disambiguated.append((slug_before, stem))

            cs = r.checksum()
            state.resources[f"{kind}:{gam_id}"] = ResourceEntry(
                gam_id=gam_id,
                checksum_local=cs,
                checksum_remote=cs,
                last_modified_remote=datetime.now(tz=UTC),
            )
            typer.echo(f"  ✓ {yaml_path.relative_to(root)}")

    store.save(state)
    typer.echo(f"\nState: {len(state.resources)} resources tracked in .gampan/state.json")
    if disambiguated:
        typer.echo("\nNote: the following filenames were disambiguated (duplicate slug):")
        for orig, final in disambiguated:
            typer.echo(f"  {orig} → {final}")


def _resolve_kinds(resource: str) -> list[str]:
    if resource == "all":
        return ["NativeStyle", "CreativeTemplate"]
    if resource == "native-styles":
        return ["NativeStyle"]
    if resource == "creative-templates":
        return ["CreativeTemplate"]
    raise typer.BadParameter(f"unknown resource '{resource}'")
