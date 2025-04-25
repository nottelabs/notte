from pathlib import Path
from typing import Any, Self

import toml
from pydantic import BaseModel


class FrozenConfig(BaseModel):
    verbose: bool = False

    class Config:
        frozen: bool = True
        extra: str = "forbid"

    def _copy_and_validate(self: Self, **kwargs: Any) -> Self:
        # kwargs should be validated before being passed to model_copy
        _ = self.model_validate(kwargs)
        config = self.model_copy(deep=True, update=kwargs)
        return config

    def set_verbose(self: Self) -> Self:
        return self._copy_and_validate(verbose=True)

    def set_deep_verbose(self: Self, value: bool = True) -> Self:
        updated_fields: dict[str, Any] = {
            field: config.set_deep_verbose(value=value)
            for field, config in self.__dict__.items()
            if isinstance(config, FrozenConfig)
        }
        if "session" in updated_fields:
            updated_fields["force_session"] = True
        return self._copy_and_validate(**updated_fields, verbose=value)


class TomlConfig(BaseModel):
    @classmethod
    def from_toml(cls, path: str | Path = "config.toml") -> Self:
        """Load settings from a TOML file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with path.open("r") as f:
            toml_data = toml.load(f)
            return cls.model_validate(toml_data)
