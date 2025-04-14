from typing import Any

from typing_extensions import override


class Singleton(type):
    _instances: dict[type, Any] = {}

    @override
    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        if cls not in cls._instances:  # pyright: ignore[reportUnnecessaryContains]
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]
