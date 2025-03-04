from typing import Any, TypeVar

from pydantic import BaseModel

TConfig = TypeVar("TConfig", bound="FrozenConfig")


class FrozenConfig(BaseModel):
    verbose: bool = False

    class Config:
        frozen: bool = True
        extra: str = "forbid"

    def _copy_and_validate(self: TConfig, **kwargs: Any) -> TConfig:
        # kwargs should be validated before being passed to model_copy
        _ = self.model_validate(kwargs)
        config = self.model_copy(deep=True, update=kwargs)
        return config

    def set_verbose(self: TConfig) -> TConfig:
        return self._copy_and_validate(verbose=True)

    def set_deep_verbose(self: TConfig) -> TConfig:
        updated_fields: dict[str, Any] = {
            field: value.set_deep_verbose() for field, value in self.__dict__.items() if isinstance(value, FrozenConfig)
        }
        if "env" in updated_fields:
            updated_fields["force_env"] = True
        return self._copy_and_validate(**updated_fields, verbose=True)
