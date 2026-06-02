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
    # Env slice populated with the migrated entry, keyed by gam_id.
    assert "default" in state.environments
    assert "943048" in state.environments["default"].resources
    # v1 top-level fields are retained during the transitional period so
    # unmigrated callers (refresh, executor) keep working until they're
    # rewritten env-aware.
    assert "NativeStyle:_gam_id:943048" in state.resources
    assert state.resources["NativeStyle:_gam_id:943048"].gam_id == "943048"


def test_migration_backfills_kind_from_v1_composite_key(tmp_path: Path) -> None:
    """v1 ResourceEntry had no ``kind`` field; v2's ``scope_current_to_env``
    filters out entries where ``entry.kind`` is falsy. Migration must
    recover the kind from the v1 composite key (e.g.
    ``NativeStyle:_gam_id:943048`` or ``NativeStyle:foo``) so migrated
    resources stay visible to multi-env plan/apply.
    """
    v1_blob = """{
      "schema_version": 1,
      "network_code": "217",
      "resources": {
        "NativeStyle:_gam_id:943048": {
          "gam_id": "943048",
          "checksum_local": "a",
          "checksum_remote": "a"
        },
        "CreativeTemplate:user-authored": {
          "gam_id": "777001",
          "checksum_local": "b",
          "checksum_remote": "b"
        }
      }
    }"""
    p = tmp_path / "state.json"
    p.write_text(v1_blob)
    state = StateStore(p).load()
    default = state.environments["default"]
    assert default.resources["943048"].kind == "NativeStyle"
    assert default.resources["777001"].kind == "CreativeTemplate"


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
