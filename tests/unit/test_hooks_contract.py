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
