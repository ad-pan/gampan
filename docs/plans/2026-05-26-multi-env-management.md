# Multi-Environment Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add first-class multi-environment support to gampan — declarative `environments:` config, env-keyed `_gam_ids` identity, gam_id-keyed env-nested state, and a process-boundary hook framework with `transform` / `reverse-transform` / `before-apply` subcommands.

**Architecture:** YAML carries gampan-managed metadata (`_gam_ids`, `_envs`) that the core strips before invoking user hooks. State is sync metadata only, keyed by GAM-issued `gam_id`, nested by environment. Hooks are external executables invoked via JSON-over-stdio subcommands with an exit-code convention (0/64/other) that keeps every hook subcommand optional. The reference spec is `docs/specs/2026-05-26-multi-env-management-design.md`.

**Tech Stack:** Python 3.12+, Pydantic v2, typer, pytest, ruamel.yaml (round-trippable YAML), structlog. v1 single-env code paths must keep passing existing tests.

---

## File Structure

### New files

| Path | Responsibility |
|---|---|
| `src/gampan/core/env/__init__.py` | Marker. |
| `src/gampan/core/env/config.py` | `Environment` pydantic model + helpers for the `environments:` block. |
| `src/gampan/core/env/filter.py` | `_envs` annotation rules. |
| `src/gampan/core/identity/__init__.py` | Marker. |
| `src/gampan/core/identity/resolve.py` | Read `_gam_ids[env]` per resource; emit CREATE intent for missing; strip gampan-managed metadata. |
| `src/gampan/core/hooks/__init__.py` | Marker. |
| `src/gampan/core/hooks/discover.py` | Per-subcommand path resolution (`hook.<sub>.path` → `hook.path` → `.gampan/hooks` → none). |
| `src/gampan/core/hooks/invoke.py` | Subprocess invocation; JSON in/out; exit-code dispatch. |
| `src/gampan/core/hooks/contract.py` | Pydantic models for hook input/output payloads. |
| `examples/multi-env/.gampan/config.yml` | Worked-example config. |
| `examples/multi-env/.gampan/hooks` | Worked-example hook script (kind-aware prefix convention). |
| `examples/multi-env/README.md` | Walkthrough of the example. |
| `tests/unit/test_env_config.py` | |
| `tests/unit/test_env_filter.py` | |
| `tests/unit/test_identity_resolve.py` | |
| `tests/unit/test_hooks_discover.py` | |
| `tests/unit/test_hooks_invoke.py` | |
| `tests/unit/test_hooks_contract.py` | |
| `tests/unit/test_cli_multi_env.py` | CLI flag plumbing (`--env`, `--envs`, `--all-envs`). |
| `tests/unit/test_state_v2_migration.py` | v1 → v2 state migration. |

### Modified files

| Path | What changes |
|---|---|
| `src/gampan/core/fs/config.py` | Add `Environment`, `EnvironmentVars`, `HookConfig`, `HookSubconfig` models; add `environments:` and `hook:` fields; mark `env:` deprecated. |
| `src/gampan/core/state/schema.py` | Add `EnvironmentSlice`; add `environments: dict[str, EnvironmentSlice]` on `State`; bump `schema_version` to 2; add `kind` + `name_hint` to `ResourceEntry`. |
| `src/gampan/core/state/store.py` | Detect schema v1 documents on load and migrate into v2 in-memory; preserve atomic write. |
| `src/gampan/core/fs/loader.py` | Read `_gam_ids` (dict) and `_envs`; accept legacy scalar `_gam_id` with deprecation warning. |
| `src/gampan/core/fs/writer.py` | Add helper to scaffold a YAML with `_gam_ids: {}`; update existing scaffolder. |
| `src/gampan/core/engine/executor.py` | Replace scalar `_gam_id` write-back with `_gam_ids[env]` write-back; thread `env` through executor. |
| `src/gampan/core/engine/diff.py` | Accept `gam_id` directly from identity resolver instead of from `key` parsing; carry `env` into `Change`. |
| `src/gampan/cli/plan.py` | Plumb `--env`/`--all-envs`; call identity resolve + filter + transform hook before diff. |
| `src/gampan/cli/apply.py` | Plumb `--env`; call `before-apply` hook between plan and executor. |
| `src/gampan/cli/refresh.py` | Plumb `--env`; restrict refresh to one env slice. |
| `src/gampan/cli/import_cmd.py` | Plumb `--envs`; per-env fetch + `reverse-transform` + cross-env reconciliation. |

---

## Phase 1 — Foundations

### Task 1: Config schema — `environments:` + `hook:` blocks; deprecate `env:`

**Files:**
- Modify: `src/gampan/core/fs/config.py`
- Test: `tests/unit/test_env_config.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_env_config.py
import pytest
from gampan.core.fs.config import Config, Environment, HookConfig, HookSubconfig


def test_minimal_config_no_environments() -> None:
    cfg = Config(network_code="217")
    assert cfg.environments == {}
    assert cfg.hook is None


def test_environments_block_parsed() -> None:
    cfg = Config(
        network_code="217",
        environments={
            "dev": Environment(vars={"ad_unit": "12345"}),
            "prod": Environment(vars={"ad_unit": "67890"}),
        },
    )
    assert set(cfg.environments) == {"dev", "prod"}
    assert cfg.environments["dev"].vars == {"ad_unit": "12345"}


def test_hook_config_hierarchical() -> None:
    cfg = Config(
        network_code="217",
        hook=HookConfig(
            path="./hooks/all.py",
            **{"before-apply": HookSubconfig(path="./hooks/policy.sh")},
        ),
    )
    assert cfg.hook.path == "./hooks/all.py"
    assert cfg.hook.before_apply.path == "./hooks/policy.sh"


def test_env_field_accepted_with_warning(caplog) -> None:
    Config(network_code="217", env="prod")
    assert any(
        "env:` field is removed" in r.message for r in caplog.records
    )
```

- [ ] **Step 2: Run test, expect failure**

Run: `uv run pytest tests/unit/test_env_config.py -v`
Expected: ImportError for `Environment`, `HookConfig`, `HookSubconfig`.

- [ ] **Step 3: Implement the models**

```python
# src/gampan/core/fs/config.py — append/replace as below
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

_log = logging.getLogger(__name__)


class Environment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    vars: dict[str, Any] = Field(default_factory=dict)


class HookSubconfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    path: str


class HookConfig(BaseModel):
    # Keys with dashes ("before-apply") use alias; Python attrs use underscores.
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    path: str | None = None
    transform: HookSubconfig | None = None
    reverse_transform: HookSubconfig | None = Field(default=None, alias="reverse-transform")
    before_apply: HookSubconfig | None = Field(default=None, alias="before-apply")


class Config(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    network_code: str
    env: str | None = None  # v1 legacy; warned + ignored
    default_dry_run: bool = False
    sources: dict[str, list[str]] | list[str] | None = None
    include_archived: bool = False

    environments: dict[str, Environment] = Field(default_factory=dict)
    hook: HookConfig | None = None

    @model_validator(mode="after")
    def _warn_on_legacy_env(self) -> "Config":
        if self.env is not None:
            _log.warning(
                "the `env:` field is removed in v1.x; "
                "move it to a comment or use `environments:`"
            )
        return self
```

- [ ] **Step 4: Run test, expect pass**

Run: `uv run pytest tests/unit/test_env_config.py -v`
Expected: 4 passed.

- [ ] **Step 5: Verify v1 single-env config still loads**

Run: `uv run pytest tests/unit/test_cli_init.py tests/unit/test_cli_main.py -v`
Expected: still green (no regression on `env:` field or v1 callers).

- [ ] **Step 6: Commit**

```bash
git add src/gampan/core/fs/config.py tests/unit/test_env_config.py
git commit -m "feat(config): add environments and hook blocks; deprecate env field"
```

---

### Task 2: State schema v2 — env-nested, gam_id-keyed entries

**Files:**
- Modify: `src/gampan/core/state/schema.py`
- Test: `tests/unit/test_state_schema_v2.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_state_schema_v2.py
from gampan.core.state.schema import EnvironmentSlice, ResourceEntry, State


def test_v2_state_round_trips() -> None:
    state = State(
        schema_version=2,
        network_code="217",
        environments={
            "dev": EnvironmentSlice(
                resources={
                    "943048": ResourceEntry(
                        kind="NativeStyle",
                        name_hint="article-card",
                        gam_id="943048",
                        checksum_local="a",
                        checksum_remote="a",
                    )
                }
            ),
            "prod": EnvironmentSlice(
                resources={
                    "961262": ResourceEntry(
                        kind="NativeStyle",
                        name_hint="article-card",
                        gam_id="961262",
                        checksum_local="a",
                        checksum_remote="a",
                    )
                }
            ),
        },
    )
    blob = state.model_dump_json()
    again = State.model_validate_json(blob)
    assert again.environments["dev"].resources["943048"].name_hint == "article-card"


def test_v1_compat_fields_still_exist() -> None:
    # v1 callers must continue to load v1 state files; v1 fields remain optional.
    state = State(
        schema_version=1,
        network_code="217",
        resources={
            "NativeStyle:_gam_id:943048": ResourceEntry(
                kind="NativeStyle",
                name_hint="article-card",
                gam_id="943048",
                checksum_local="a",
                checksum_remote="a",
            )
        },
    )
    assert state.environments == {}
    assert state.resources["NativeStyle:_gam_id:943048"].gam_id == "943048"
```

- [ ] **Step 2: Run test, expect failure**

Run: `uv run pytest tests/unit/test_state_schema_v2.py -v`
Expected: ImportError on `EnvironmentSlice`; `kind` / `name_hint` not accepted on `ResourceEntry`.

- [ ] **Step 3: Update the schema**

```python
# src/gampan/core/state/schema.py — full replacement
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ResourceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gam_id: str
    kind: str | None = None              # v2 only; None on v1 entries
    name_hint: str | None = None         # v2 only; informational
    checksum_local: str
    checksum_remote: str
    last_modified_remote: datetime | None = None
    drift_acknowledged: bool = True


class EnvironmentSlice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    last_apply_at: datetime | None = None
    last_apply_tool_version: str | None = None
    resources: dict[str, ResourceEntry] = Field(default_factory=dict)


class State(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    network_code: str

    # v1 fields (still present so v1 files load unchanged)
    last_apply_at: datetime | None = None
    last_apply_tool_version: str | None = None
    resources: dict[str, ResourceEntry] = Field(default_factory=dict)

    # v2 field
    environments: dict[str, EnvironmentSlice] = Field(default_factory=dict)
```

- [ ] **Step 4: Run test, expect pass**

Run: `uv run pytest tests/unit/test_state_schema_v2.py -v`
Expected: 2 passed.

- [ ] **Step 5: Verify v1 state tests still pass**

Run: `uv run pytest tests/unit/test_state_store.py -v` (if present) and `uv run pytest tests/unit/test_engine_diff.py -v`
Expected: still green.

- [ ] **Step 6: Commit**

```bash
git add src/gampan/core/state/schema.py tests/unit/test_state_schema_v2.py
git commit -m "feat(state): schema v2 with env-nested, gam_id-keyed entries"
```

---

### Task 3: State v1 → v2 auto-migration on load

**Files:**
- Modify: `src/gampan/core/state/store.py`
- Test: `tests/unit/test_state_v2_migration.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_state_v2_migration.py
from pathlib import Path

from gampan.core.state.store import StateStore


def test_v1_state_loads_and_migrates_to_default_env(tmp_path: Path) -> None:
    v1_blob = """{
      "schema_version": 1,
      "network_code": "217",
      "resources": {
        "NativeStyle:_gam_id:943048": {
          "gam_id": "943048",
          "checksum_local": "a",
          "checksum_remote": "a"
        }
      }
    }"""
    p = tmp_path / "state.json"
    p.write_text(v1_blob)
    store = StateStore(p)
    state = store.load()
    # Migrated in memory:
    assert state.schema_version == 2
    assert "default" in state.environments
    assert "943048" in state.environments["default"].resources
    # Original top-level resources cleared after migration so the engine has one source of truth.
    assert state.resources == {}


def test_v2_state_loads_unchanged(tmp_path: Path) -> None:
    v2_blob = """{
      "schema_version": 2,
      "network_code": "217",
      "environments": {
        "dev": {
          "resources": {
            "943048": {
              "gam_id": "943048",
              "kind": "NativeStyle",
              "name_hint": "article-card",
              "checksum_local": "a",
              "checksum_remote": "a"
            }
          }
        }
      }
    }"""
    p = tmp_path / "state.json"
    p.write_text(v2_blob)
    state = StateStore(p).load()
    assert state.schema_version == 2
    assert state.environments["dev"].resources["943048"].name_hint == "article-card"
```

- [ ] **Step 2: Run test, expect failure**

Run: `uv run pytest tests/unit/test_state_v2_migration.py -v`
Expected: assertion fails — v1 state loads with `schema_version == 1` and empty `environments`.

- [ ] **Step 3: Add migration to the store**

```python
# src/gampan/core/state/store.py — replace load()
def load(self) -> State:
    if not self.path.exists():
        raise StateError(f"state file not found: {self.path}")
    try:
        state = State.model_validate_json(self.path.read_text())
    except Exception as e:
        raise StateError(f"state file corrupted ({self.path}): {e}") from e
    return _migrate_v1_to_v2(state)


def _migrate_v1_to_v2(state: State) -> State:
    if state.schema_version >= 2:
        return state
    # Pull each v1 entry into environments.default.resources keyed by gam_id.
    from gampan.core.state.schema import EnvironmentSlice  # local import to avoid cycle
    default = EnvironmentSlice(
        last_apply_at=state.last_apply_at,
        last_apply_tool_version=state.last_apply_tool_version,
        resources={entry.gam_id: entry for entry in state.resources.values()},
    )
    return state.model_copy(update={
        "schema_version": 2,
        "environments": {"default": default},
        "resources": {},
        "last_apply_at": None,
        "last_apply_tool_version": None,
    })
```

- [ ] **Step 4: Run test, expect pass**

Run: `uv run pytest tests/unit/test_state_v2_migration.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/gampan/core/state/store.py tests/unit/test_state_v2_migration.py
git commit -m "feat(state): auto-migrate v1 state files to v2 on load"
```

---

### Task 4: YAML loader — `_gam_ids` dict + `_envs`; legacy scalar `_gam_id` compat

**Files:**
- Modify: `src/gampan/core/fs/loader.py`
- Test: `tests/unit/test_loader_v1_x.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_loader_v1_x.py
from pathlib import Path

from gampan.core.fs.config import Config, Environment
from gampan.core.fs.loader import load_all


def _write(p: Path, body: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)


def test_loader_reads_gam_ids_dict(tmp_path: Path) -> None:
    _write(
        tmp_path / "native-styles" / "article-card.yaml",
        """kind: NativeStyle
name: article-card
_gam_ids:
  dev: "943048"
  prod: "961262"
size: {width: 1, height: 1, is_fluid: false}
template_id: 1
html: "<div/>"
css: ""
status: ACTIVE
""",
    )
    out = load_all(
        tmp_path,
        Config(
            network_code="217",
            environments={"dev": Environment(), "prod": Environment()},
        ),
    )
    [item] = out
    assert item["_gam_ids"] == {"dev": "943048", "prod": "961262"}
    assert "_gam_id" not in item


def test_loader_accepts_scalar_gam_id_with_warning(tmp_path: Path, caplog) -> None:
    _write(
        tmp_path / "native-styles" / "article-card.yaml",
        """kind: NativeStyle
_gam_id: "943048"
name: article-card
size: {width: 1, height: 1, is_fluid: false}
template_id: 1
html: "<div/>"
css: ""
status: ACTIVE
""",
    )
    out = load_all(tmp_path, Config(network_code="217"))
    [item] = out
    # Scalar surfaced as both keys so migration can rewrite on next apply.
    assert item["_gam_id"] == "943048"
    assert any("scalar `_gam_id` is deprecated" in r.message for r in caplog.records)


def test_loader_rejects_undeclared_env_in_gam_ids(tmp_path: Path) -> None:
    import pytest
    from gampan.core.errors import SchemaError

    _write(
        tmp_path / "native-styles" / "foo.yaml",
        """kind: NativeStyle
name: foo
_gam_ids: { staging: "1" }
size: {width: 1, height: 1, is_fluid: false}
template_id: 1
html: "<div/>"
css: ""
status: ACTIVE
""",
    )
    with pytest.raises(SchemaError, match="staging"):
        load_all(
            tmp_path,
            Config(
                network_code="217",
                environments={"dev": Environment(), "prod": Environment()},
            ),
        )
```

- [ ] **Step 2: Run test, expect failure**

Run: `uv run pytest tests/unit/test_loader_v1_x.py -v`
Expected: failures on all three (loader does not yet recognise `_gam_ids` keys; no env-key validation).

- [ ] **Step 3: Update the loader**

Modify the per-file path inside `load_all` / `_read_yaml` to:

1. After parsing the YAML dict, if it contains a scalar `_gam_id`, log the deprecation warning (`"scalar _gam_id is deprecated; will rewrite as _gam_ids on next apply"`) and keep the field; downstream identity-resolve handles it.
2. If `_gam_ids` is present and is a dict, validate every key appears in `config.environments` (when `config.environments` is non-empty). Raise `SchemaError` listing the offending YAML path and unknown env name.
3. Leave the data dict as-is — stripping happens in `core/identity/resolve.py` (Task 5).

Implementation sketch (replace the validation pass in `_read_yaml`):

```python
def _validate_gam_ids(data: dict, yaml_path: Path, config: Config) -> None:
    if not config.environments:
        return  # single-env mode; _gam_ids dict allowed but not validated against env list
    gam_ids = data.get("_gam_ids")
    if gam_ids is None:
        return
    if not isinstance(gam_ids, dict):
        raise SchemaError(f"{yaml_path}: `_gam_ids` must be a mapping, got {type(gam_ids).__name__}")
    unknown = set(gam_ids) - set(config.environments)
    if unknown:
        raise SchemaError(
            f"{yaml_path}: `_gam_ids` references undeclared env(s): {sorted(unknown)}"
        )


def _warn_scalar_gam_id(data: dict, yaml_path: Path) -> None:
    if "_gam_id" in data:
        _log.warning(
            "%s: scalar `_gam_id` is deprecated; will rewrite as `_gam_ids` on next apply",
            yaml_path,
        )
```

Call both from the per-file path after `validate_resource(data, repo_root)`.

- [ ] **Step 4: Run test, expect pass**

Run: `uv run pytest tests/unit/test_loader_v1_x.py -v`
Expected: 3 passed.

- [ ] **Step 5: Verify v1 loader tests still pass**

Run: `uv run pytest tests/unit/test_loader.py -v` (if present)
Expected: still green.

- [ ] **Step 6: Commit**

```bash
git add src/gampan/core/fs/loader.py tests/unit/test_loader_v1_x.py
git commit -m "feat(loader): accept _gam_ids dict; warn on scalar _gam_id"
```

---

### Task 5: Identity resolve module

**Files:**
- Create: `src/gampan/core/identity/__init__.py`
- Create: `src/gampan/core/identity/resolve.py`
- Test: `tests/unit/test_identity_resolve.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_identity_resolve.py
from gampan.core.identity.resolve import resolve_identity, ResolvedResource


def test_dict_form_returns_env_gam_id() -> None:
    raw = {
        "kind": "NativeStyle",
        "name": "article-card",
        "_gam_ids": {"dev": "943048", "prod": "961262"},
        "size": {"width": 1, "height": 1, "is_fluid": False},
    }
    out = resolve_identity(raw, env="dev")
    assert isinstance(out, ResolvedResource)
    assert out.gam_id == "943048"
    assert "_gam_ids" not in out.payload
    assert out.payload["name"] == "article-card"


def test_missing_env_yields_create_intent() -> None:
    raw = {"kind": "NativeStyle", "name": "new", "_gam_ids": {"prod": "1"}}
    out = resolve_identity(raw, env="dev")
    assert out.gam_id is None  # CREATE intent
    assert out.create_intent is True


def test_scalar_form_migrates_in_memory() -> None:
    raw = {"kind": "NativeStyle", "name": "legacy", "_gam_id": "943048"}
    out = resolve_identity(raw, env="dev")
    assert out.gam_id == "943048"
    # scalar treated as "same id for every env"
    assert out.from_legacy_scalar is True
    assert "_gam_id" not in out.payload


def test_envs_annotation_returned_for_filter_decision() -> None:
    raw = {"kind": "NativeStyle", "_envs": ["dev"], "name": "x"}
    out = resolve_identity(raw, env="dev")
    assert out.envs == ["dev"]
    assert "_envs" not in out.payload
```

- [ ] **Step 2: Run test, expect failure**

Run: `uv run pytest tests/unit/test_identity_resolve.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement the module**

```python
# src/gampan/core/identity/resolve.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ResolvedResource:
    gam_id: str | None
    create_intent: bool
    envs: list[str] | None        # None ⇒ "participate in all declared envs"
    from_legacy_scalar: bool
    payload: dict[str, Any]       # raw dict with gampan-managed metadata stripped


_MANAGED_KEYS = ("_gam_ids", "_gam_id", "_envs")


def resolve_identity(raw: dict[str, Any], env: str) -> ResolvedResource:
    """Read gampan-managed metadata, decide identity, return a clean payload.

    Strips `_gam_ids`, `_gam_id`, `_envs` from the returned payload so the
    hook (and downstream stages) see a clean resource.
    """
    gam_ids_dict = raw.get("_gam_ids")
    scalar_gam_id = raw.get("_gam_id")
    envs = raw.get("_envs")

    gam_id: str | None = None
    from_scalar = False
    if isinstance(gam_ids_dict, dict):
        gam_id = gam_ids_dict.get(env)
    elif scalar_gam_id is not None:
        # legacy v1 scalar: same id in every env the resource participates in
        gam_id = str(scalar_gam_id)
        from_scalar = True

    payload = {k: v for k, v in raw.items() if k not in _MANAGED_KEYS}
    return ResolvedResource(
        gam_id=gam_id,
        create_intent=gam_id is None,
        envs=list(envs) if isinstance(envs, list) else None,
        from_legacy_scalar=from_scalar,
        payload=payload,
    )
```

- [ ] **Step 4: Run test, expect pass**

Run: `uv run pytest tests/unit/test_identity_resolve.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/gampan/core/identity/ tests/unit/test_identity_resolve.py
git commit -m "feat(identity): resolve _gam_ids[env], strip managed metadata"
```

---

### Task 6: `_envs` filter module

**Files:**
- Create: `src/gampan/core/env/__init__.py`
- Create: `src/gampan/core/env/filter.py`
- Test: `tests/unit/test_env_filter.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_env_filter.py
from gampan.core.env.filter import participates_in_env


def test_absent_envs_participates_in_all() -> None:
    assert participates_in_env(envs=None, env="dev") is True
    assert participates_in_env(envs=None, env="prod") is True


def test_explicit_envs_list() -> None:
    assert participates_in_env(envs=["dev"], env="dev") is True
    assert participates_in_env(envs=["dev"], env="prod") is False


def test_empty_envs_excludes_everywhere() -> None:
    assert participates_in_env(envs=[], env="dev") is False
    assert participates_in_env(envs=[], env="prod") is False
```

- [ ] **Step 2: Run test, expect failure**

Run: `uv run pytest tests/unit/test_env_filter.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# src/gampan/core/env/filter.py
from __future__ import annotations


def participates_in_env(envs: list[str] | None, env: str) -> bool:
    """True if a resource whose `_envs` is `envs` should participate in `env`.

    None ⇒ "all declared envs" (participates everywhere).
    [] ⇒ "park" state (participates nowhere).
    """
    if envs is None:
        return True
    return env in envs
```

- [ ] **Step 4: Run test, expect pass**

Run: `uv run pytest tests/unit/test_env_filter.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/gampan/core/env/ tests/unit/test_env_filter.py
git commit -m "feat(env): filter resources by _envs annotation"
```

---

### Task 7: Executor write-back — replace scalar `_gam_id` with `_gam_ids[env]`

**Files:**
- Modify: `src/gampan/core/engine/executor.py`
- Test: `tests/unit/test_executor_gam_ids_writeback.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_executor_gam_ids_writeback.py
from pathlib import Path

from gampan.core.engine.executor import stamp_gam_id_into_yaml


def test_new_dict_form_added(tmp_path: Path) -> None:
    p = tmp_path / "x.yaml"
    p.write_text("kind: NativeStyle\nname: foo\n")
    stamp_gam_id_into_yaml(p, gam_id="943048", env="dev")
    text = p.read_text()
    assert "_gam_ids:" in text
    assert "dev:" in text
    assert "'943048'" in text or "\"943048\"" in text or "943048" in text


def test_existing_dict_extended(tmp_path: Path) -> None:
    p = tmp_path / "x.yaml"
    p.write_text(
        "kind: NativeStyle\n_gam_ids:\n  dev: '943048'\nname: foo\n"
    )
    stamp_gam_id_into_yaml(p, gam_id="961262", env="prod")
    text = p.read_text()
    assert "dev:" in text and "943048" in text  # preserved
    assert "prod:" in text and "961262" in text  # added


def test_scalar_gam_id_migrated_on_writeback(tmp_path: Path) -> None:
    p = tmp_path / "x.yaml"
    p.write_text("kind: NativeStyle\n_gam_id: '943048'\nname: foo\n")
    stamp_gam_id_into_yaml(p, gam_id="943048", env="dev")
    text = p.read_text()
    assert "_gam_id:" not in text.splitlines()[1] or "_gam_ids" in text
    assert "_gam_ids:" in text
    assert "dev:" in text and "943048" in text
```

- [ ] **Step 2: Run test, expect failure**

Run: `uv run pytest tests/unit/test_executor_gam_ids_writeback.py -v`
Expected: failures — current `stamp_gam_id_into_yaml` writes scalar only.

- [ ] **Step 3: Update the executor's stamp helper**

Modify `stamp_gam_id_into_yaml` (currently at `executor.py:107`) so it accepts an `env: str` argument and writes the dict form. Behavior:

- If `_gam_ids` exists as a dict, set `_gam_ids[env] = gam_id`.
- If `_gam_id` (scalar) exists, delete it and write `_gam_ids: { env: gam_id }` in its place (migration).
- If neither exists, insert `_gam_ids: { env: gam_id }` immediately after `kind:` (same position the scalar used).

Use `ruamel.yaml` round-trip mode (already used in the file) to preserve comments and `!file` references.

Update every call site (`executor.py` apply CREATE handler) to pass the current env.

- [ ] **Step 4: Run test, expect pass**

Run: `uv run pytest tests/unit/test_executor_gam_ids_writeback.py -v`
Expected: 3 passed.

- [ ] **Step 5: Verify existing executor tests still pass**

Run: `uv run pytest tests/unit/test_engine_executor.py -v`
Expected: still green (may require small fixture updates to pass `env`; do them in this commit).

- [ ] **Step 6: Commit**

```bash
git add src/gampan/core/engine/executor.py tests/unit/test_executor_gam_ids_writeback.py tests/unit/test_engine_executor.py
git commit -m "feat(executor): write back _gam_ids[env] dict; migrate scalar form"
```

---

## Phase 2 — Hook Framework

### Task 8: Hook discovery — per-subcommand path resolution

**Files:**
- Create: `src/gampan/core/hooks/__init__.py`
- Create: `src/gampan/core/hooks/discover.py`
- Test: `tests/unit/test_hooks_discover.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_hooks_discover.py
import os
from pathlib import Path

import pytest

from gampan.core.fs.config import HookConfig, HookSubconfig
from gampan.core.hooks.discover import HookNotFound, HookPathError, resolve_hook_path


def _make_exec(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("#!/usr/bin/env bash\nexit 64\n")
    os.chmod(p, 0o755)


def test_default_location_file(tmp_path: Path) -> None:
    _make_exec(tmp_path / ".gampan" / "hooks")
    assert resolve_hook_path(tmp_path, hook=None, subcommand="transform") == tmp_path / ".gampan" / "hooks"


def test_default_location_py_alternative(tmp_path: Path) -> None:
    _make_exec(tmp_path / ".gampan" / "hooks.py")
    assert resolve_hook_path(tmp_path, hook=None, subcommand="transform") == tmp_path / ".gampan" / "hooks.py"


def test_default_ambiguous_raises(tmp_path: Path) -> None:
    _make_exec(tmp_path / ".gampan" / "hooks")
    _make_exec(tmp_path / ".gampan" / "hooks.py")
    with pytest.raises(HookPathError, match="ambiguous"):
        resolve_hook_path(tmp_path, hook=None, subcommand="transform")


def test_no_hook_returns_none(tmp_path: Path) -> None:
    assert resolve_hook_path(tmp_path, hook=None, subcommand="transform") is None


def test_subcommand_specific_path_overrides(tmp_path: Path) -> None:
    _make_exec(tmp_path / ".gampan" / "hooks")
    _make_exec(tmp_path / "hooks" / "policy.sh")
    hook = HookConfig(
        path=".gampan/hooks",
        **{"before-apply": HookSubconfig(path="hooks/policy.sh")},
    )
    assert resolve_hook_path(tmp_path, hook, "transform") == tmp_path / ".gampan" / "hooks"
    assert resolve_hook_path(tmp_path, hook, "before-apply") == tmp_path / "hooks" / "policy.sh"


def test_config_path_missing_file_raises(tmp_path: Path) -> None:
    hook = HookConfig(path="does-not-exist")
    with pytest.raises(HookPathError, match="does-not-exist"):
        resolve_hook_path(tmp_path, hook, "transform")


def test_config_path_not_executable_raises(tmp_path: Path) -> None:
    p = tmp_path / "script.py"
    p.write_text("#!/usr/bin/env python3\n")
    # no chmod
    hook = HookConfig(path="script.py")
    with pytest.raises(HookPathError, match="executable"):
        resolve_hook_path(tmp_path, hook, "transform")
```

- [ ] **Step 2: Run test, expect failure**

Run: `uv run pytest tests/unit/test_hooks_discover.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# src/gampan/core/hooks/discover.py
from __future__ import annotations

import os
from pathlib import Path

from gampan.core.fs.config import HookConfig

_SUBCOMMAND_ATTR = {
    "transform": "transform",
    "reverse-transform": "reverse_transform",
    "before-apply": "before_apply",
}


class HookPathError(Exception):
    """Raised when a hook path is declared but invalid (missing, non-executable, ambiguous)."""


class HookNotFound(Exception):
    """Sentinel — not raised; reserved for callers that want to distinguish missing from invalid."""


def resolve_hook_path(repo_root: Path, hook: HookConfig | None, subcommand: str) -> Path | None:
    """Return an executable path, or None for pass-through mode."""
    # 1. Per-subcommand config override
    if hook is not None:
        attr = _SUBCOMMAND_ATTR.get(subcommand)
        sub = getattr(hook, attr, None) if attr else None
        if sub is not None and sub.path is not None:
            return _check(repo_root, sub.path)
        # 2. Shared config fallback
        if hook.path is not None:
            return _check(repo_root, hook.path)
        return None  # config block present but no path for this sub — pass-through

    # 3. Default location
    file_form = repo_root / ".gampan" / "hooks"
    py_form = repo_root / ".gampan" / "hooks.py"
    if file_form.exists() and py_form.exists():
        raise HookPathError(
            "ambiguous default hook location: both .gampan/hooks and .gampan/hooks.py exist; "
            "remove one or set hook.path in config"
        )
    for candidate in (file_form, py_form):
        if candidate.exists():
            if not os.access(candidate, os.X_OK):
                raise HookPathError(f"{candidate} exists but is not executable")
            return candidate
    return None


def _check(repo_root: Path, raw: str) -> Path:
    p = (repo_root / raw).resolve() if not Path(raw).is_absolute() else Path(raw)
    if not p.exists():
        raise HookPathError(f"hook path {raw} does not exist (resolved: {p})")
    if not os.access(p, os.X_OK):
        raise HookPathError(f"hook path {raw} is not executable (resolved: {p})")
    return p
```

- [ ] **Step 4: Run test, expect pass**

Run: `uv run pytest tests/unit/test_hooks_discover.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/gampan/core/hooks/ tests/unit/test_hooks_discover.py
git commit -m "feat(hooks): per-subcommand path resolution"
```

---

### Task 9: Hook invocation — subprocess + JSON in/out + exit codes

**Files:**
- Create: `src/gampan/core/hooks/invoke.py`
- Test: `tests/unit/test_hooks_invoke.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_hooks_invoke.py
import json
import os
from pathlib import Path

import pytest

from gampan.core.hooks.invoke import (
    HookCrash,
    HookOutputError,
    HookRejected,
    invoke_hook,
)


def _script(p: Path, body: str) -> Path:
    p.write_text(body)
    os.chmod(p, 0o755)
    return p


def test_passthrough_returns_input(tmp_path: Path) -> None:
    # invoke_hook called with hook_path=None should pass through.
    result = invoke_hook(hook_path=None, subcommand="transform", payload={"resources": [1]})
    assert result == {"resources": [1]}


def test_transform_round_trip(tmp_path: Path) -> None:
    script = _script(
        tmp_path / "hook",
        """#!/usr/bin/env python3
import json, sys
i = json.load(sys.stdin)
i.setdefault("touched", True)
json.dump(i, sys.stdout)
""",
    )
    out = invoke_hook(hook_path=script, subcommand="transform", payload={"resources": []})
    assert out == {"resources": [], "touched": True}


def test_exit_64_returns_passthrough(tmp_path: Path) -> None:
    script = _script(tmp_path / "hook", "#!/usr/bin/env bash\nexit 64\n")
    out = invoke_hook(hook_path=script, subcommand="transform", payload={"resources": [1]})
    # Treated as "not implemented" — caller receives the input unchanged.
    assert out == {"resources": [1]}


def test_reject_envelope_recognised(tmp_path: Path) -> None:
    script = _script(
        tmp_path / "hook",
        """#!/usr/bin/env python3
import json, sys
sys.stdout.write(json.dumps({"reject": "destructive"}))
sys.exit(1)
""",
    )
    with pytest.raises(HookRejected, match="destructive"):
        invoke_hook(hook_path=script, subcommand="before-apply", payload={})


def test_non_zero_without_reject_is_crash(tmp_path: Path) -> None:
    script = _script(tmp_path / "hook", "#!/usr/bin/env bash\necho boom >&2\nexit 1\n")
    with pytest.raises(HookCrash, match="boom"):
        invoke_hook(hook_path=script, subcommand="transform", payload={})


def test_non_json_stdout_is_output_error(tmp_path: Path) -> None:
    script = _script(tmp_path / "hook", "#!/usr/bin/env bash\necho not-json\n")
    with pytest.raises(HookOutputError):
        invoke_hook(hook_path=script, subcommand="transform", payload={})
```

- [ ] **Step 2: Run test, expect failure**

Run: `uv run pytest tests/unit/test_hooks_invoke.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# src/gampan/core/hooks/invoke.py
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


class HookRejected(Exception):
    """before-* hook returned an exit non-zero (≠64) plus {reject: ...} on stdout."""
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class HookCrash(Exception):
    """Hook exited non-zero (≠64) with no parseable reject envelope."""


class HookOutputError(Exception):
    """Hook exited 0 but its stdout was not valid JSON."""


def invoke_hook(
    *,
    hook_path: Path | None,
    subcommand: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Run a hook subcommand, return the parsed JSON output (or the input for pass-through)."""
    if hook_path is None:
        return payload  # pass-through mode

    proc = subprocess.run(
        [str(hook_path), subcommand],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )

    if proc.returncode == 64:
        # Not implemented — caller treats as pass-through / approve.
        return payload

    if proc.returncode != 0:
        # Try the reject envelope first.
        try:
            envelope = json.loads(proc.stdout) if proc.stdout.strip() else None
        except json.JSONDecodeError:
            envelope = None
        if isinstance(envelope, dict) and "reject" in envelope:
            raise HookRejected(str(envelope["reject"]))
        raise HookCrash(
            f"{hook_path.name} {subcommand} exited {proc.returncode}: {proc.stderr.strip()}"
        )

    try:
        return json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError as e:
        raise HookOutputError(
            f"{hook_path.name} {subcommand} produced non-JSON stdout: {proc.stdout[:200]!r}"
        ) from e
```

- [ ] **Step 4: Run test, expect pass**

Run: `uv run pytest tests/unit/test_hooks_invoke.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/gampan/core/hooks/invoke.py tests/unit/test_hooks_invoke.py
git commit -m "feat(hooks): subprocess invocation with exit-code contract"
```

---

### Task 10: Hook contract payload models

**Files:**
- Create: `src/gampan/core/hooks/contract.py`
- Test: `tests/unit/test_hooks_contract.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_hooks_contract.py
from gampan.core.hooks.contract import (
    BeforeApplyInput,
    BeforeApplyPlanAction,
    TransformInput,
    TransformOutput,
)


def test_transform_input_serializes() -> None:
    payload = TransformInput(
        environment="dev",
        config={"network_code": "217", "vars": {"ad_unit": "1"}},
        resources=[{"kind": "NativeStyle", "name": "foo"}],
    ).to_payload()
    assert payload["schema_version"] == 1
    assert payload["environment"] == "dev"
    assert payload["resources"][0]["kind"] == "NativeStyle"


def test_transform_output_validates() -> None:
    out = TransformOutput.from_payload({"schema_version": 1, "resources": [{"kind": "X"}]})
    assert out.resources == [{"kind": "X"}]


def test_before_apply_input_carries_gam_id() -> None:
    payload = BeforeApplyInput(
        environment="prod",
        config={"network_code": "217", "vars": {}},
        plan=[
            BeforeApplyPlanAction(
                action="create",
                kind="NativeStyle",
                name="new-thing",
                post_transform_name="new-thing",
                gam_id=None,
                changes=[],
            ),
            BeforeApplyPlanAction(
                action="update",
                kind="NativeStyle",
                name="existing",
                post_transform_name="existing",
                gam_id="961262",
                changes=[{"field": "css", "from": "<sha256:a>", "to": "<sha256:b>"}],
            ),
        ],
    ).to_payload()
    assert payload["plan"][0]["gam_id"] is None
    assert payload["plan"][1]["gam_id"] == "961262"
```

- [ ] **Step 2: Run test, expect failure**

Run: `uv run pytest tests/unit/test_hooks_contract.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# src/gampan/core/hooks/contract.py
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class TransformInput:
    environment: str
    config: dict[str, Any]
    resources: list[dict[str, Any]]

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "environment": self.environment,
            "config": self.config,
            "resources": list(self.resources),
        }


@dataclass(frozen=True)
class TransformOutput:
    resources: list[dict[str, Any]]

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "TransformOutput":
        return cls(resources=list(payload.get("resources", [])))


@dataclass(frozen=True)
class BeforeApplyPlanAction:
    action: Literal["create", "update", "delete"]
    kind: str
    name: str
    post_transform_name: str
    gam_id: str | None
    changes: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class BeforeApplyInput:
    environment: str
    config: dict[str, Any]
    plan: list[BeforeApplyPlanAction]

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "environment": self.environment,
            "config": self.config,
            "plan": [asdict(a) for a in self.plan],
        }
```

- [ ] **Step 4: Run test, expect pass**

Run: `uv run pytest tests/unit/test_hooks_contract.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/gampan/core/hooks/contract.py tests/unit/test_hooks_contract.py
git commit -m "feat(hooks): contract payload models for transform and before-apply"
```

---

## Phase 3 — Hook Integration

### Task 11: Wire `transform` + identity resolve into the plan pipeline

**Files:**
- Modify: `src/gampan/cli/plan.py`
- Modify: `src/gampan/core/engine/diff.py` (accept env + pre-resolved gam_id directly)
- Test: `tests/unit/test_cli_plan_multi_env.py` (new)

- [ ] **Step 1: Write the failing integration-flavor test**

```python
# tests/unit/test_cli_plan_multi_env.py
import os
from pathlib import Path

from typer.testing import CliRunner

from gampan.cli.main import app

runner = CliRunner()


def _scaffold(tmp_path: Path) -> Path:
    (tmp_path / ".gampan").mkdir()
    (tmp_path / ".gampan" / "config.yml").write_text(
        """network_code: "217"
environments:
  dev: {}
  prod: {}
"""
    )
    hook = tmp_path / ".gampan" / "hooks"
    hook.write_text(
        """#!/usr/bin/env python3
import json, sys
sub = sys.argv[1]
inp = json.load(sys.stdin)
if sub == "transform":
    env = inp["environment"]
    for r in inp["resources"]:
        if env == "dev":
            r["name"] = f"[dev] {r['name']}"
    json.dump({"schema_version": 1, "resources": inp["resources"]}, sys.stdout)
else:
    sys.exit(64)
"""
    )
    os.chmod(hook, 0o755)
    return tmp_path


def test_plan_dev_invokes_transform(tmp_path: Path, monkeypatch) -> None:
    repo = _scaffold(tmp_path)
    (repo / "native-styles").mkdir()
    (repo / "native-styles" / "article-card.yaml").write_text(
        """kind: NativeStyle
name: article-card
size: {width: 1, height: 1, is_fluid: false}
template_id: 1
html: "<div/>"
css: ""
status: ACTIVE
"""
    )
    monkeypatch.chdir(repo)
    result = runner.invoke(app, ["plan", "--env", "dev", "--offline"], catch_exceptions=False)
    # The plan should print "[dev] article-card" because the hook decorated it.
    assert "[dev] article-card" in result.stdout
    assert result.exit_code in (0, 2)  # 0 or "pending changes"
```

(`--offline` flag may or may not exist; if not, use a network stub fixture pattern already in `tests/unit/test_cli_plan.py`. The point of this test is to verify the hook is invoked and identity resolve runs before the diff.)

- [ ] **Step 2: Run test, expect failure**

Run: `uv run pytest tests/unit/test_cli_plan_multi_env.py -v`
Expected: `[dev] article-card` not in output (plan does not yet invoke transform).

- [ ] **Step 3: Modify plan.py**

In `cli/plan.py`, after `load_all(...)` and before passing resources to the diff engine:

1. Read `--env` (Task 13 plumbs the flag itself; this task assumes it has been parsed).
2. For each loaded resource dict, call `resolve_identity(raw, env=cli_env)` → `ResolvedResource`.
3. Filter out resources where `participates_in_env(resolved.envs, cli_env)` is False.
4. Build `TransformInput(environment=cli_env, config={...}, resources=[r.payload for r in survivors])`.
5. Call `invoke_hook(hook_path=resolve_hook_path(repo_root, cfg.hook, "transform"), subcommand="transform", payload=ti.to_payload())`.
6. The hook output's `resources` is the transformed list — zip back against survivors to recover their pre-resolved gam_ids.
7. Pass `(gam_id, transformed_dict)` pairs into the existing `diff_resources(...)` call (it already accepts `gam_id`-based identity per its signature comment at line 199).

Sketch (insertion in `cli/plan.py`):

```python
from gampan.core.env.filter import participates_in_env
from gampan.core.hooks.contract import TransformInput, TransformOutput
from gampan.core.hooks.discover import resolve_hook_path
from gampan.core.hooks.invoke import invoke_hook
from gampan.core.identity.resolve import resolve_identity

# ... after load_all ...
env = ctx.params["env"] or _single_env_or_default(cfg)
hook_path = resolve_hook_path(repo_root, cfg.hook, "transform")
resolved = [resolve_identity(raw, env=env) for raw in raw_resources]
participating = [r for r in resolved if participates_in_env(r.envs, env)]
ti = TransformInput(
    environment=env,
    config={"network_code": cfg.network_code, "vars": cfg.environments.get(env, Environment()).vars},
    resources=[r.payload for r in participating],
)
transformed = TransformOutput.from_payload(invoke_hook(
    hook_path=hook_path, subcommand="transform", payload=ti.to_payload()
)).resources
# Pair each transformed dict with the gam_id we resolved before transform.
pairs = list(zip([r.gam_id for r in participating], transformed))
```

When `environments` is empty (v1 single-env mode), `env` defaults to `"default"` and the rest of the flow is unchanged.

- [ ] **Step 4: Run test, expect pass**

Run: `uv run pytest tests/unit/test_cli_plan_multi_env.py -v`
Expected: passes; `[dev] article-card` appears in plan output.

- [ ] **Step 5: Verify v1 plan tests still pass**

Run: `uv run pytest tests/unit/test_cli_plan.py -v`
Expected: still green.

- [ ] **Step 6: Commit**

```bash
git add src/gampan/cli/plan.py src/gampan/core/engine/diff.py tests/unit/test_cli_plan_multi_env.py
git commit -m "feat(plan): invoke transform hook after identity resolve and env filter"
```

---

### Task 12: Wire `before-apply` into the apply pipeline

**Files:**
- Modify: `src/gampan/cli/apply.py`
- Test: `tests/unit/test_cli_apply_before_apply.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_cli_apply_before_apply.py
import os
from pathlib import Path

from typer.testing import CliRunner

from gampan.cli.main import app

runner = CliRunner()


def _hook_rejects_all(tmp_path: Path) -> None:
    h = tmp_path / ".gampan" / "hooks"
    h.parent.mkdir(parents=True, exist_ok=True)
    h.write_text(
        """#!/usr/bin/env python3
import json, sys
sub = sys.argv[1]
if sub == "before-apply":
    sys.stdout.write(json.dumps({"reject": "test rejection"}))
    sys.exit(1)
sys.exit(64)
"""
    )
    os.chmod(h, 0o755)


def test_before_apply_reject_blocks_apply(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".gampan").mkdir()
    (tmp_path / ".gampan" / "config.yml").write_text(
        'network_code: "217"\nenvironments:\n  dev: {}\n'
    )
    _hook_rejects_all(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app, ["apply", "--env", "dev", "--auto-approve"], catch_exceptions=False
    )
    assert result.exit_code != 0
    assert "test rejection" in result.stdout + result.stderr
```

- [ ] **Step 2: Run test, expect failure**

Run: `uv run pytest tests/unit/test_cli_apply_before_apply.py -v`
Expected: hook is never invoked; apply proceeds.

- [ ] **Step 3: Modify apply.py**

After the plan is computed and before the executor runs:

1. Build `BeforeApplyInput` from the plan (one `BeforeApplyPlanAction` per `Change`).
2. Resolve hook path with `subcommand="before-apply"`.
3. Call `invoke_hook(...)`. Catch `HookRejected`: print the reason via the existing renderer, exit non-zero (use exit code 3 — same as user-aborted in v1 — or a new code if §6.1 specifies). Catch `HookCrash`: surface the error and exit non-zero. Pass-through (no hook / exit 64) ⇒ proceed.
4. For large blob fields (HTML/CSS), populate `changes[].from` / `changes[].to` with `"<sha256:...>"` strings rather than full content. Helper: hash both sides via `hashlib.sha256(...).hexdigest()[:16]`.

- [ ] **Step 4: Run test, expect pass**

Run: `uv run pytest tests/unit/test_cli_apply_before_apply.py -v`
Expected: passes; "test rejection" appears in output, exit code non-zero.

- [ ] **Step 5: Verify v1 apply tests still pass**

Run: `uv run pytest tests/unit/test_cli_apply.py tests/unit/test_engine_executor.py -v`
Expected: still green.

- [ ] **Step 6: Commit**

```bash
git add src/gampan/cli/apply.py tests/unit/test_cli_apply_before_apply.py
git commit -m "feat(apply): invoke before-apply hook with reject envelope handling"
```

---

### Task 13: CLI flags — `--env` (plan/apply/refresh), `--envs` (import), `--all-envs` (plan)

**Files:**
- Modify: `src/gampan/cli/plan.py`, `src/gampan/cli/apply.py`, `src/gampan/cli/refresh.py`, `src/gampan/cli/import_cmd.py`
- Test: `tests/unit/test_cli_multi_env.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_cli_multi_env.py
from pathlib import Path

from typer.testing import CliRunner

from gampan.cli.main import app

runner = CliRunner()


def _multi_env_repo(tmp_path: Path) -> Path:
    (tmp_path / ".gampan").mkdir()
    (tmp_path / ".gampan" / "config.yml").write_text(
        'network_code: "217"\nenvironments:\n  dev: {}\n  prod: {}\n'
    )
    return tmp_path


def test_plan_requires_env_when_envs_declared(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(_multi_env_repo(tmp_path))
    result = runner.invoke(app, ["plan"], catch_exceptions=False)
    assert result.exit_code != 0
    assert "--env" in result.stdout + result.stderr


def test_plan_unknown_env_lists_choices(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(_multi_env_repo(tmp_path))
    result = runner.invoke(app, ["plan", "--env", "staging"], catch_exceptions=False)
    assert result.exit_code != 0
    assert "staging" in result.stdout + result.stderr
    assert "dev" in result.stdout + result.stderr  # valid choice listed
    assert "prod" in result.stdout + result.stderr


def test_v1_single_env_plan_works_without_env_flag(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".gampan").mkdir()
    (tmp_path / ".gampan" / "config.yml").write_text('network_code: "217"\n')
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["plan", "--offline"], catch_exceptions=False)
    # Should not error on the missing --env flag.
    assert "--env" not in (result.stderr or "")


def test_import_envs_flag_parsed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(_multi_env_repo(tmp_path))
    result = runner.invoke(
        app, ["import", "--envs", "dev,prod", "--dry-run"], catch_exceptions=False
    )
    # Should accept the flag without parser error.
    assert "no such option" not in (result.stderr or "").lower()
```

- [ ] **Step 2: Run test, expect failure**

Run: `uv run pytest tests/unit/test_cli_multi_env.py -v`
Expected: every test fails — flags not yet defined.

- [ ] **Step 3: Add flags + validation**

In `plan.py`, `apply.py`, `refresh.py`:

```python
@app.command()
def plan(
    env: str | None = typer.Option(None, "--env", "-e", help="Target environment."),
    all_envs: bool = typer.Option(False, "--all-envs", help="Plan every declared environment."),
    # ... existing options ...
) -> None:
    cfg = load_config(...)
    if cfg.environments:
        if not env and not all_envs:
            typer.echo(
                f"--env is required (declared envs: {sorted(cfg.environments)})", err=True
            )
            raise typer.Exit(2)
        if env and env not in cfg.environments:
            typer.echo(
                f"unknown env {env!r}; declared: {sorted(cfg.environments)}", err=True
            )
            raise typer.Exit(2)
        targets = sorted(cfg.environments) if all_envs else [env]
    else:
        targets = ["default"]  # v1 single-env path
    for target in targets:
        _run_plan(repo_root, cfg, env=target)
```

In `import_cmd.py`:

```python
@app.command("import")
def import_cmd(
    envs: str | None = typer.Option(None, "--envs", help="Comma-separated envs to import."),
    # ...
) -> None:
    if cfg.environments:
        if not envs:
            typer.echo("--envs is required when environments: is declared", err=True)
            raise typer.Exit(2)
        env_list = [e.strip() for e in envs.split(",")]
        unknown = set(env_list) - set(cfg.environments)
        if unknown:
            typer.echo(f"unknown env(s): {sorted(unknown)}", err=True)
            raise typer.Exit(2)
    else:
        env_list = ["default"]
    # ... pass env_list down to the importer (Task 14) ...
```

`apply.py` and `refresh.py` only accept `--env` (single value); reject `--all-envs`.

- [ ] **Step 4: Run test, expect pass**

Run: `uv run pytest tests/unit/test_cli_multi_env.py -v`
Expected: 4 passed.

- [ ] **Step 5: Run full CLI test suite**

Run: `uv run pytest tests/unit/test_cli_*.py -v`
Expected: still green (v1 paths preserved by the `if cfg.environments` guard).

- [ ] **Step 6: Commit**

```bash
git add src/gampan/cli/ tests/unit/test_cli_multi_env.py
git commit -m "feat(cli): add --env, --envs, --all-envs flags with validation"
```

---

### Task 14: Import multi-env — `reverse-transform` + cross-env reconciliation

**Files:**
- Modify: `src/gampan/cli/import_cmd.py`
- Test: `tests/unit/test_cli_import_multi_env.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_cli_import_multi_env.py
import json
import os
from pathlib import Path

import pytest

from gampan.cli.import_cmd import reconcile_across_envs


def _r(name: str, gam_id: str, css: str = "") -> dict:
    return {
        "kind": "NativeStyle",
        "name": name,
        "gam_id": gam_id,
        "css": css,
        "size": {"width": 1, "height": 1, "is_fluid": False},
    }


def test_same_canonical_name_both_envs_identical_merges_one_file() -> None:
    out = reconcile_across_envs(
        per_env={
            "dev": [_r("article-card", "943048")],
            "prod": [_r("article-card", "961262")],
        }
    )
    [merged] = out
    assert merged.canonical_name == "article-card"
    assert merged.gam_ids == {"dev": "943048", "prod": "961262"}
    assert merged.envs is None  # participates in all declared envs


def test_one_env_only_writes_envs_annotation() -> None:
    out = reconcile_across_envs(
        per_env={
            "dev": [_r("experiment", "999000")],
            "prod": [],
        }
    )
    [merged] = out
    assert merged.envs == ["dev"]
    assert merged.gam_ids == {"dev": "999000"}


def test_different_content_raises_conflict() -> None:
    with pytest.raises(Exception, match="article-card"):
        reconcile_across_envs(
            per_env={
                "dev": [_r("article-card", "1", css="A")],
                "prod": [_r("article-card", "2", css="B")],
            }
        )
```

- [ ] **Step 2: Run test, expect failure**

Run: `uv run pytest tests/unit/test_cli_import_multi_env.py -v`
Expected: ImportError on `reconcile_across_envs`.

- [ ] **Step 3: Implement reconciliation**

```python
# src/gampan/cli/import_cmd.py — add reconcile_across_envs

from dataclasses import dataclass
from typing import Any


@dataclass
class MergedResource:
    kind: str
    canonical_name: str
    gam_ids: dict[str, str]
    payload: dict[str, Any]
    envs: list[str] | None  # None ⇒ participates in all declared envs


class ImportConflict(Exception):
    """Same canonical name appears in multiple envs with differing content."""


def reconcile_across_envs(
    per_env: dict[str, list[dict[str, Any]]],
    declared_envs: list[str] | None = None,
) -> list[MergedResource]:
    """Fold per-env reverse-transformed resource lists into canonical YAML descriptors."""
    declared = declared_envs or list(per_env)
    # Group by (kind, canonical_name)
    grouped: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for env, resources in per_env.items():
        for r in resources:
            key = (r["kind"], r["name"])
            grouped.setdefault(key, {})[env] = r

    merged: list[MergedResource] = []
    for (kind, name), per_env_resource in grouped.items():
        # Strip gam_id before comparing content; gam_id is per-env by design.
        normalized = {
            env: {k: v for k, v in res.items() if k not in ("gam_id",)}
            for env, res in per_env_resource.items()
        }
        first_env, first_norm = next(iter(normalized.items()))
        for env, norm in normalized.items():
            if norm != first_norm:
                raise ImportConflict(
                    f"{kind}:{name}: content differs between envs {first_env} and {env}"
                )
        gam_ids = {env: res["gam_id"] for env, res in per_env_resource.items()}
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
```

Then wire it into `import` flow:

1. For each env in `env_list`, fetch via existing client adapter.
2. Run `reverse-transform` hook per env (if hook present and implements the subcommand).
3. Call `reconcile_across_envs(per_env=..., declared_envs=list(cfg.environments))`.
4. Write one canonical YAML per `MergedResource`, including `_gam_ids: <merged.gam_ids>` and (if non-None) `_envs: <merged.envs>`.
5. Write per-env state entries keyed by gam_id.

- [ ] **Step 4: Run test, expect pass**

Run: `uv run pytest tests/unit/test_cli_import_multi_env.py -v`
Expected: 3 passed.

- [ ] **Step 5: Verify v1 import tests still pass**

Run: `uv run pytest tests/unit/test_cli_import.py tests/integration/test_import_e2e.py -v`
Expected: still green (single-env path = single key in `per_env`, no reconciliation conflicts possible).

- [ ] **Step 6: Commit**

```bash
git add src/gampan/cli/import_cmd.py tests/unit/test_cli_import_multi_env.py
git commit -m "feat(import): multi-env fetch + reverse-transform + cross-env reconciliation"
```

---

## Phase 4 — Polish

### Task 15: Worked example under `examples/multi-env/`

**Files:**
- Create: `examples/multi-env/.gampan/config.yml`
- Create: `examples/multi-env/.gampan/hooks`
- Create: `examples/multi-env/README.md`
- Create: `examples/multi-env/native-styles/article-card.yaml` (illustrative; not loaded by any test)

- [ ] **Step 1: Write the config**

```yaml
# examples/multi-env/.gampan/config.yml
network_code: "21700000000"
environments:
  dev: {}
  prod: {}
```

- [ ] **Step 2: Write the hook script**

```python
#!/usr/bin/env python3
"""Multi-env reference hook: kind-aware `[dev] ` name prefix."""
import json
import sys

DECORATED_KINDS = {"NativeStyle", "NativeFormat"}
DEV_PREFIX = "[dev] "

sub = sys.argv[1] if len(sys.argv) > 1 else ""
inp = json.load(sys.stdin)

if sub == "transform":
    env = inp["environment"]
    out = []
    for r in inp["resources"]:
        if r["kind"] in DECORATED_KINDS and env == "dev":
            r["name"] = f"{DEV_PREFIX}{r['name']}"
        out.append(r)
    json.dump({"schema_version": 1, "resources": out}, sys.stdout)

elif sub == "reverse-transform":
    env = inp["environment"]
    out = []
    for r in inp["resources"]:
        if r["kind"] not in DECORATED_KINDS:
            out.append(r)
            continue
        decorated = r["name"].startswith(DEV_PREFIX)
        if env == "dev":
            if not decorated:
                continue
            r["name"] = r["name"][len(DEV_PREFIX):]
        else:
            if decorated:
                continue
        out.append(r)
    json.dump({"schema_version": 1, "resources": out}, sys.stdout)

else:
    sys.exit(64)  # not implemented
```

Then `chmod +x examples/multi-env/.gampan/hooks`.

- [ ] **Step 3: Write the README**

`examples/multi-env/README.md` — narrative walkthrough that mirrors §7 of the spec. Sections:

1. What this example shows (single network, prefix-based env split, kind-aware hook).
2. The config file.
3. The hook script (link inline).
4. Sample YAML with `_gam_ids` populated.
5. `deploy/dev` and `deploy/prod` CI commands.
6. Pointer back to the spec.

- [ ] **Step 4: Commit**

```bash
git add examples/multi-env/
git commit -m "docs(examples): multi-env reference (prefix convention)"
```

---

### Task 16: Self-review pass — coverage map vs. spec, error handling polish

**Files:**
- Modify: `docs/specs/2026-05-26-multi-env-management-design.md` (cross-reference only)
- Modify: any error-message strings flagged during review

- [ ] **Step 1: Manual coverage check**

Walk §1–§12 of the spec and tick off the task that implements each requirement. Flag any gap.

Known mapping (verify each):

| Spec section | Task(s) |
|---|---|
| §3.1 Environment concept | Task 1 |
| §3.2 Hook concept | Tasks 8, 9, 10 |
| §3.3 `_envs` annotation | Tasks 4, 6 |
| §4.1 Pipeline | Task 11 |
| §4.2 Modules | Tasks 1, 5, 6, 8, 9, 10, 11 |
| §5.1 Config schema | Task 1 |
| §5.2 YAML annotations | Tasks 4, 5 |
| §5.3 `transform` hook | Tasks 10, 11 |
| §5.3 `reverse-transform` | Tasks 10, 14 |
| §5.3 `before-apply` | Tasks 10, 12 |
| §5.4 State v2 | Tasks 2, 3 |
| §6.1 CLI flags | Task 13 |
| §6.2 Hook discovery | Task 8 |
| §6.3 Import multi-env | Task 14 |
| §6.4 Safety (explicit `--env`) | Task 13 |
| §7 Worked example | Task 15 |
| §8 Lifecycle scenarios | Covered by tests across Tasks 11–14 |
| §9 Error handling rows | Verified per row in this task |
| §10 Backward compat | Tasks 3 (state), 4 (scalar `_gam_id`), 1 (`env:` warning) |

- [ ] **Step 2: Add any missing error messages**

For each row of §9 that doesn't have a clear matching test, add a small unit test that triggers the condition. Examples likely uncovered after the earlier tasks:

- "Same gam_id appears in two different YAMLs" — add a load-time check in `loader.py` and a test in `tests/unit/test_loader_v1_x.py` (extend that file rather than make a new one).
- "Write-back of `_gam_ids` after CREATE fails" — add a test in `tests/unit/test_executor_gam_ids_writeback.py` that makes the file read-only and verifies a warning is logged with the captured gam_id.

- [ ] **Step 3: Run the full test suite**

Run: `uv run pytest -v`
Expected: all green.

- [ ] **Step 4: Run lint + type checks**

Run: `uv run ruff check src tests && uv run mypy src`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add src tests
git commit -m "chore(multi-env): error-message polish and spec coverage gaps"
```

---

## Summary

16 tasks across 4 phases:

- **Phase 1 (Tasks 1–7):** foundations — config, state schema + migration, loader, identity resolve, env filter, executor write-back.
- **Phase 2 (Tasks 8–10):** hook framework — discovery, invocation, contract.
- **Phase 3 (Tasks 11–14):** integration — `transform` in plan, `before-apply` in apply, CLI flags, multi-env import.
- **Phase 4 (Tasks 15–16):** worked example + spec-coverage self-review.

Each task is TDD: failing test → minimal implementation → verify v1 paths still pass → commit. Run `uv run pytest -v` after each task.

After Task 16, the branch `feat/multi-env-management` is ready for PR against `main`.
