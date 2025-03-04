from notte.common.config import FrozenConfig


class SubConfig(FrozenConfig):
    max_steps: int = 10


class SubSubConfig(FrozenConfig):
    hello: str = "world"
    config: SubConfig = SubConfig()


def test_frozen_config_initialization():
    config = FrozenConfig()
    assert config.verbose is False


def test_set_verbose():
    config = FrozenConfig()
    updated_config = config.set_verbose()
    assert updated_config.verbose is True


def test_set_deep_verbose():
    subclass_config = SubConfig()
    assert subclass_config.verbose is False
    updated_config = subclass_config.set_deep_verbose()
    assert updated_config.verbose is True
    assert updated_config.max_steps == 10


def test_set_deep_verbose_subclass():
    config = SubSubConfig()
    assert config.config.verbose is False
    assert config.verbose is False
    updated_config = config.set_deep_verbose()
    assert updated_config.verbose is True
    assert updated_config.config.verbose is True
