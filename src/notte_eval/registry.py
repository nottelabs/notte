from typing import Any, Callable

class EvaluatorRegistry:
    _classes: dict[str, Any] = {}

    @classmethod
    def register(cls, name: str) -> Callable[..., Any]:
        def decorator(registered_class: type):
            cls._classes[name] = registered_class
            return registered_class

        return decorator

    @classmethod
    def get_all_classes(cls):
        return cls._classes
