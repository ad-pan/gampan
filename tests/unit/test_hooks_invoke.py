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
