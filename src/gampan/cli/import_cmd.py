"""`gampan import` — pull remote resources into local YAML + state."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import typer
from ruamel.yaml import YAML

from gampan.cli._envs import resolve_multi_envs
from gampan.cli.plan import _load_config, build_clients
from gampan.core.fs.loader import CONVENTION_DIRS
from gampan.core.fs.writer import slugify, write_resource
from gampan.core.state.schema import ResourceEntry
from gampan.core.state.store import StateStore

# Maps each managed kind to the on-disk directories that may hold its
# imported YAMLs. NativeStyle only lives under ``native-styles/``;
# CreativeTemplate is split between ``creative-templates/`` (regular
# templates) and ``native-formats/`` (the Google-shipped native ad format
# templates carried as CreativeTemplates with ``native_eligible=true``).
# ``--resource native-styles`` therefore avoids re-parsing the (large)
# native-formats / creative-templates directories.
_KIND_DIRS: dict[str, tuple[str, ...]] = {
    "NativeStyle": ("native-styles",),
    "CreativeTemplate": ("creative-templates", "native-formats"),
}


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
    envs: str | None = typer.Option(
        None,
        "--envs",
        help=(
            "Comma-separated env list to import into (e.g. `dev,prod`). Required "
            "when environments are declared in .gampan/config.yml; ignored in v1 "
            "single-env mode. Each name must be a key under `environments:`."
        ),
    ),
) -> None:
    """Pull GAM resources into YAML + populate state.json."""
    root = Path.cwd()
    try:
        cfg = _load_config(root)
    except FileNotFoundError as e:
        typer.echo("Not a gampan repo (missing .gampan/config.yml). Run `gampan init` first.")
        raise typer.Exit(code=1) from e

    # Task 13 parses and validates --envs; the actual multi-env
    # reconciliation (per-env _gam_ids write-back, reverse-transform) lands
    # in Task 14. Until then, ``target_envs`` only affects flag validation:
    # v1 single-env import still runs unchanged when the list is the
    # placeholder ``[default]``.
    target_envs = resolve_multi_envs(cfg, envs)
    assert target_envs, "resolve_multi_envs guarantees a non-empty list"

    effective_include_archived = (
        cfg.include_archived if include_archived is None else include_archived
    )

    clients = build_clients(cfg.network_code)

    store = StateStore(root / ".gampan" / "state.json")
    state = store.load_or_empty(network_code=cfg.network_code)

    kinds = _resolve_kinds(resource)
    seen_slugs: set[str] = set()
    disambiguated: list[tuple[str, str]] = []

    # Pre-scan only the directories the active --resource filter cares
    # about; a NativeStyle-only import does not need to parse the
    # creative-templates dir.
    existing_yaml_by_gam_id = _collect_existing_yaml_by_gam_id(root, kinds)
    orphans_removed: list[Path] = []

    for kind in kinds:
        for gam_id, r in clients[kind].list(include_archived=effective_include_archived):
            slug_before = slugify(r.name)
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
        typer.echo("\nRemoved orphan YAML(s) after rename (same _gam_id, new slug):")
        for p in orphans_removed:
            typer.echo(f"  - {p.relative_to(root)}")


def _collect_existing_yaml_by_gam_id(root: Path, kinds: list[str]) -> dict[str, Path]:
    """Return ``{_gam_id: yaml_path}`` for previously-imported YAMLs.

    Only scans directories that map to *kinds* (a NativeStyle-only run
    skips the creative-templates dir entirely). User-authored YAMLs
    (no ``_gam_id`` field yet) are intentionally skipped — import must
    never touch a file the operator authored locally. Per-file parse
    errors are swallowed so a malformed YAML elsewhere does not block
    the rename-detection path.
    """
    dirs = {d for k in kinds for d in _KIND_DIRS.get(k, ())}
    # Defensive: a future ``--resource`` value that the kind map does not
    # cover falls back to the full convention sweep rather than silently
    # skipping rename detection.
    if not dirs:
        dirs = set(CONVENTION_DIRS)

    yaml_safe = YAML(typ="safe")
    out: dict[str, Path] = {}
    for dirname in dirs:
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
    """Delete a rename-orphaned YAML and its ``.html`` / ``.css`` siblings.

    ``write_resource`` emits ``<stem>.<kind-suffix>.yaml`` plus the side
    files the ``!file`` references resolve to; rename detection only
    knows about the YAML, so glob the rest by stripping ``.yaml`` from
    the filename and matching siblings.
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
