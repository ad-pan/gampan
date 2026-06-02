"""Shared CLI helpers for resolving ``--env`` / ``--envs`` / ``--all-envs``.

When ``cfg.environments`` is empty the user is running gampan in v1
single-env mode and the flags are accepted but ignored (the placeholder
env name ``"default"`` keeps identity resolution + hooks wired up exactly
as v1 did). When ``cfg.environments`` is non-empty the flag becomes
required and unknown env names are rejected with a typer exit code 2 plus
a message listing the valid choices.
"""

from __future__ import annotations

from collections.abc import Iterable

import typer

from gampan.core.fs.config import Config

# Internal placeholder used when no `environments:` block is declared.
# Identity resolve + hooks still need *some* env string to thread through;
# v1 callers historically used "default" so we keep that contract.
V1_DEFAULT_ENV = "default"


def _format_choices(names: Iterable[str]) -> str:
    return ", ".join(sorted(names))


def resolve_single_env(cfg: Config, requested: str | None, *, flag: str = "--env") -> str:
    """Resolve a single env name for ``plan`` / ``apply`` / ``refresh``.

    - When ``cfg.environments`` is empty: ignore ``requested`` and return
      :data:`V1_DEFAULT_ENV` so v1 behaviour is preserved bit-for-bit.
    - Otherwise: ``requested`` must be supplied AND must be a key in
      ``cfg.environments``. Unknown / missing values raise
      ``typer.Exit(code=2)`` with the list of valid envs.
    """
    if not cfg.environments:
        return V1_DEFAULT_ENV

    if requested is None:
        typer.echo(
            f"Error: {flag} is required when environments are declared in "
            f".gampan/config.yml. Valid envs: {_format_choices(cfg.environments)}",
            err=True,
        )
        raise typer.Exit(code=2)

    if requested not in cfg.environments:
        typer.echo(
            f"Error: unknown env '{requested}'. "
            f"Valid envs: {_format_choices(cfg.environments)}",
            err=True,
        )
        raise typer.Exit(code=2)

    return requested


def resolve_plan_targets(
    cfg: Config, requested: str | None, *, all_envs: bool
) -> list[str]:
    """Resolve ``plan``'s env target list (supports ``--all-envs``).

    Returns the list of env names to iterate over. In v1 single-env mode
    the list is always ``[V1_DEFAULT_ENV]`` regardless of flags.
    """
    if all_envs and requested is not None:
        typer.echo(
            "Error: --env and --all-envs are mutually exclusive.",
            err=True,
        )
        raise typer.Exit(code=2)

    if not cfg.environments:
        # v1 mode — flags are ignored, single placeholder env.
        return [V1_DEFAULT_ENV]

    if all_envs:
        return sorted(cfg.environments)

    return [resolve_single_env(cfg, requested)]


def resolve_import_envs(cfg: Config) -> list[str]:
    """Resolve ``import``'s env list — always ALL declared environments.

    ``import`` reads the whole GAM network (one network per config) and
    writes canonical YAMLs covering every environment at once. Computing the
    ``_envs`` annotation correctly requires seeing *every* declared env: a
    resource present only in an imported subset would be mis-tagged as
    subset-only, silently dropping the other envs' gam_ids. ``import``
    therefore takes no env flag — it always covers all declared envs.

    v1 single-env mode (no ``environments:`` block) returns the placeholder
    env so downstream single-env code paths keep working.
    """
    if not cfg.environments:
        return [V1_DEFAULT_ENV]
    return sorted(cfg.environments)
