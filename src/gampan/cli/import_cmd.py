"""`gampan import` — pull remote resources into local YAML + state."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer
from ruamel.yaml import YAML

from gampan.cli._envs import resolve_multi_envs
from gampan.cli.plan import _load_config, build_clients
from gampan.core.engine.executor import stamp_gam_id_into_yaml
from gampan.core.fs.loader import CONVENTION_DIRS
from gampan.core.fs.writer import slugify, write_resource
from gampan.core.hooks.contract import TransformInput, TransformOutput
from gampan.core.hooks.discover import resolve_hook_path
from gampan.core.hooks.invoke import invoke_hook
from gampan.core.state.schema import EnvironmentSlice, ResourceEntry
from gampan.core.state.store import StateStore


@dataclass
class MergedResource:
    """A canonical resource folded across one-or-more environments.

    ``gam_ids`` always carries one entry per env where the resource was
    observed; ``envs`` records the explicit ``_envs:`` annotation when
    the resource does NOT participate in every declared env (None ⇒
    participates in all declared envs, so the annotation can be omitted).
    """

    kind: str
    canonical_name: str
    gam_ids: dict[str, str]
    payload: dict[str, Any]
    envs: list[str] | None


class ImportConflict(Exception):
    """Same canonical name appears in multiple envs with differing content."""


def reconcile_across_envs(
    per_env: dict[str, list[dict[str, Any]]],
    declared_envs: list[str] | None = None,
) -> list[MergedResource]:
    """Fold per-env reverse-transformed resource lists into canonical YAML descriptors.

    Each input resource dict carries its env-side ``gam_id`` field; the
    reconciliation strips that before comparing content (gam_id is per-env
    by design and never matches across envs).

    Args:
        per_env: ``{env: [resource_dict, ...]}``. Each resource_dict must
            carry ``kind``, ``name``, and ``gam_id`` keys plus whatever
            shape the kind's model serialises to.
        declared_envs: The full set of env names the operator asked to
            import. When the per-env subset for a given resource matches
            this set the ``envs`` annotation is omitted; otherwise the
            subset is recorded so a later partial-env apply can filter.

    Raises:
        ImportConflict: Two envs produced resources with the same
            canonical name but differing content (gam_id excluded).
    """
    declared = declared_envs or list(per_env)
    grouped: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for env, resources in per_env.items():
        for r in resources:
            key = (r["kind"], r["name"])
            grouped.setdefault(key, {})[env] = r

    merged: list[MergedResource] = []
    for (kind, name), per_env_resource in grouped.items():
        normalized = {
            env: {k: v for k, v in res.items() if k != "gam_id"}
            for env, res in per_env_resource.items()
        }
        first_env, first_norm = next(iter(normalized.items()))
        for env, norm in normalized.items():
            if norm != first_norm:
                raise ImportConflict(
                    f"{kind}:{name}: content differs between envs {first_env} and {env}"
                )
        gam_ids = {env: str(res["gam_id"]) for env, res in per_env_resource.items()}
        envs_present = sorted(per_env_resource)
        envs_field = None if set(envs_present) == set(declared) else envs_present
        merged.append(
            MergedResource(
                kind=kind,
                canonical_name=name,
                gam_ids=gam_ids,
                payload=first_norm,
                envs=envs_field,
            )
        )
    return merged

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

    if cfg.environments:
        _run_multi_env_import(
            root=root,
            cfg=cfg,
            clients=clients,
            kinds=kinds,
            target_envs=target_envs,
            include_archived=effective_include_archived,
            store=store,
            state=state,
        )
        return

    # v1 single-env path — unchanged.
    seen_slugs: set[str] = set()
    disambiguated: list[tuple[str, str]] = []
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


def _run_multi_env_import(
    *,
    root: Path,
    cfg: Any,
    clients: Mapping[str, Any],
    kinds: list[str],
    target_envs: list[str],
    include_archived: bool,
    store: StateStore,
    state: Any,
) -> None:
    """Multi-env import: fetch per-env, reverse-transform, reconcile, write."""
    # 1. Fetch per env per kind; keep both the raw model (for YAML write)
    #    and a serialized dict (for reconcile content comparison).
    per_env_dicts: dict[str, list[dict[str, Any]]] = {env: [] for env in target_envs}
    # (env, kind, canonical_name) → original Resource model (any env's copy works
    # since reconcile guarantees identical content modulo gam_id).
    model_by_canonical: dict[tuple[str, str], Any] = {}

    for env in target_envs:
        env_resources: list[dict[str, Any]] = []
        for kind in kinds:
            for gam_id, r in clients[kind].list(include_archived=include_archived):
                d = r.model_dump(mode="python", exclude_none=False)
                d["kind"] = kind
                d["name"] = r.name
                d["gam_id"] = str(gam_id)
                env_resources.append(d)
                # last-write-wins; bodies are equal post-reconcile
                model_by_canonical[(kind, r.name)] = r

        # 2. reverse-transform hook (if present)
        hook_path = resolve_hook_path(root, cfg.hook, "reverse-transform")
        env_vars = cfg.environments[env].vars if env in cfg.environments else {}
        ti = TransformInput(
            environment=env,
            config={"network_code": cfg.network_code, "vars": env_vars},
            resources=env_resources,
        )
        out = invoke_hook(
            hook_path=hook_path, subcommand="reverse-transform", payload=ti.to_payload()
        )
        canonical = TransformOutput.from_payload(out).resources

        # If the hook renamed any resources, also re-key model_by_canonical so
        # the later YAML write finds the model under its canonical name.
        for orig, post in zip(env_resources, canonical, strict=False):
            new_name = post.get("name")
            kind_o = orig["kind"]
            if new_name and new_name != orig["name"]:
                m = model_by_canonical.pop((kind_o, orig["name"]), None)
                if m is not None:
                    model_by_canonical[(kind_o, new_name)] = m

        per_env_dicts[env] = canonical

    # 3. Reconcile across envs.
    try:
        merged = reconcile_across_envs(per_env_dicts, declared_envs=list(cfg.environments))
    except ImportConflict as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e

    # 4. Write each canonical YAML and per-env state.
    seen_slugs: set[str] = set()
    for mr in merged:
        model = model_by_canonical.get((mr.kind, mr.canonical_name))
        if model is None:
            # Should not happen; defense in depth.
            typer.echo(f"Error: no source model for {mr.kind}:{mr.canonical_name}", err=True)
            raise typer.Exit(code=1)
        # Ensure model name matches canonical (reverse-transform may have renamed).
        if model.name != mr.canonical_name:
            model = model.model_copy(update={"name": mr.canonical_name})

        # Scaffold YAML using any env's gam_id as the primary; we'll rewrite
        # the identity block to the full dict immediately after.
        primary_env, primary_gam_id = next(iter(mr.gam_ids.items()))
        yaml_path, _ = write_resource(
            root, model, gam_id=primary_gam_id, seen_slugs=seen_slugs
        )

        # Stamp every env's gam_id. Task 7's helper migrates the scalar
        # `_gam_id` written by write_resource into the `_gam_ids` dict on
        # the first stamp call.
        for env, gid in mr.gam_ids.items():
            stamp_gam_id_into_yaml(yaml_path, gam_id=gid, env=env)

        if mr.envs is not None:
            _stamp_envs_annotation(yaml_path, mr.envs)

        typer.echo(f"  ✓ {yaml_path.relative_to(root)}")

        # 5. Per-env state writes. Use additive v2 layout: populate
        #    state.environments[env].resources[gam_id] keyed by gam_id.
        cs = model.checksum()
        for env, gid in mr.gam_ids.items():
            slice_ = state.environments.setdefault(env, EnvironmentSlice())
            slice_.resources[gid] = ResourceEntry(
                gam_id=gid,
                kind=mr.kind,
                name_hint=mr.canonical_name,
                checksum_local=cs,
                checksum_remote=cs,
                last_modified_remote=datetime.now(tz=UTC),
            )

    store.save(state)
    n_resources = sum(len(s.resources) for s in state.environments.values())
    typer.echo(
        f"\nState: {n_resources} resources tracked in .gampan/state.json "
        f"across {len(state.environments)} env(s)"
    )


def _stamp_envs_annotation(yaml_path: Path, envs: list[str]) -> None:
    """Insert ``_envs: [...]`` line into the YAML right after ``_gam_ids:``.

    Uses ruamel round-trip so comments and side-file references survive.
    """
    yaml_rt = YAML()
    yaml_rt.default_flow_style = False
    yaml_rt.width = 2**31 - 1
    data = yaml_rt.load(yaml_path.read_text(encoding="utf-8"))
    if data is None:
        return
    keys = list(data.keys())
    if "_gam_ids" in keys:
        insert_at = keys.index("_gam_ids") + 1
    elif "kind" in keys:
        insert_at = keys.index("kind") + 1
    else:
        insert_at = 0
    data.insert(insert_at, "_envs", list(envs))
    with yaml_path.open("w", encoding="utf-8") as f:
        yaml_rt.dump(data, f)


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
