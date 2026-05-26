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
