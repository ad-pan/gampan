from __future__ import annotations


def participates_in_env(envs: list[str] | None, env: str) -> bool:
    """True if a resource whose `_envs` is `envs` should participate in `env`.

    None ⇒ "all declared envs" (participates everywhere).
    [] ⇒ "park" state (participates nowhere).
    """
    if envs is None:
        return True
    return env in envs
