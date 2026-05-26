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
