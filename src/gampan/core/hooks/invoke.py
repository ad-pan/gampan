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
