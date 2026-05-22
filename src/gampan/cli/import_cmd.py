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

# Directories scanned when locating stale imported YAMLs. Mirrors the
# layout `write_resource` writes into; native-formats holds NativeStyle-
# related CreativeTemplates so it must be swept too.
_LAYOUT_DIRS = ("native-styles", "creative-templates", "native-formats")


def run(
    resource: str = typer.Option(
        "all", "--resource", "-r", help="native-styles | creative-templates | all"
    ),
    include_archived: bool | None = typer.Option(
        None,
        "--include-archived/--no-include-archived",
        help=(
            "Include ARCHIVED remote resources. Overrides config.include_archived "
            "for this run; falls back to the config value when omitted."
        ),
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
    effective_include_archived = (
        bool(cfg.get("include_archived", False))
        if include_archived is None
        else include_archived
    )

    clients = build_clients(cfg["network_code"])

    store = StateStore(root / ".gampan" / "state.json")
    state = store.load_or_empty(network_code=cfg["network_code"])

    kinds = _resolve_kinds(resource)
    # Track seen filename stems per-run to disambiguate slug collisions.
    seen_slugs: set[str] = set()
    # Track any stems that were disambiguated so we can report them.
    disambiguated: list[tuple[str, str]] = []  # (original_slug, final_stem)

    # Map each imported YAML's ``_gam_id`` → on-disk path *before* writing.
    # When a resource has been renamed on the remote, ``write_resource`` lays
    # the file down under the new slug but the old-slug YAML (and its
    # ``.html`` / ``.css`` side files) would otherwise linger as an orphan
    # and trip ``validate_no_duplicates`` on the next plan/apply.
    existing_yaml_by_gam_id = _collect_existing_yaml_by_gam_id(root)
    orphans_removed: list[Path] = []

    for kind in kinds:
        for gam_id, r in clients[kind].list(include_archived=effective_include_archived):
            from gampan.core.fs.writer import slugify as _slugify

            slug_before = _slugify(r.name)
            yaml_path, stem = write_resource(root, r, gam_id=gam_id, seen_slugs=seen_slugs)
            if slug_before and stem != slug_before:
                disambiguated.append((slug_before, stem))

            existing_path = existing_yaml_by_gam_id.get(str(gam_id))
            if existing_path is not None and existing_path != yaml_path:
                orphans_removed.extend(_remove_orphan_yaml(existing_path))

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
    if orphans_removed:
        typer.echo(
            "\nRemoved orphan YAML(s) after rename (same _gam_id, new slug):"
        )
        for p in orphans_removed:
            typer.echo(f"  - {p.relative_to(root)}")


def _collect_existing_yaml_by_gam_id(root: Path) -> dict[str, Path]:
    """Return ``{_gam_id: yaml_path}`` for every imported YAML on disk.

    User-authored YAMLs (no ``_gam_id`` field yet) are intentionally
    skipped — import should never touch a file the operator authored
    locally. Errors loading individual files are swallowed so a stray
    malformed YAML elsewhere does not block the rename-detection path.
    """
    yaml_safe = YAML(typ="safe")
    out: dict[str, Path] = {}
    for dirname in _LAYOUT_DIRS:
        d = root / dirname
        if not d.exists():
            continue
        for yaml_path in d.glob("*.yaml"):
            try:
                data = yaml_safe.load(yaml_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            gam_id = data.get("_gam_id")
            if gam_id is None:
                continue
            out[str(gam_id)] = yaml_path
    return out


def _remove_orphan_yaml(yaml_path: Path) -> list[Path]:
    """Delete a rename-orphaned YAML and its side files.

    ``write_resource`` emits ``<stem>.<kind-suffix>.yaml`` plus optional
    ``<stem>.<kind-suffix>.html`` and ``<stem>.<kind-suffix>.css`` files
    next to it (the ``!file`` references inside the YAML). The
    rename-detection logic only knows about the YAML, so glob the rest
    by stripping ``.yaml`` from the filename and matching siblings.
    """
    removed: list[Path] = []
    if yaml_path.exists():
        yaml_path.unlink()
        removed.append(yaml_path)
    stem_with_suffix = yaml_path.name[: -len(".yaml")]
    for side in yaml_path.parent.glob(f"{stem_with_suffix}.*"):
        if side.suffix in {".html", ".css"} and side.exists():
            side.unlink()
            removed.append(side)
    return removed


def _resolve_kinds(resource: str) -> list[str]:
    if resource == "all":
        return ["NativeStyle", "CreativeTemplate"]
    if resource == "native-styles":
        return ["NativeStyle"]
    if resource == "creative-templates":
        return ["CreativeTemplate"]
    raise typer.BadParameter(f"unknown resource '{resource}'")
