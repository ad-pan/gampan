from gampan.core.identity.resolve import ResolvedResource, resolve_identity


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
