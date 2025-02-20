from typing import Any

from examples.benchmark.default import AgentBenchmark, AgentParams
from examples.benchmark.evaluators import Evaluator


class BenchmarkRegistry:
    _classes: dict[str, tuple[type[Any], type[AgentBenchmark[Any, Any]]]] = {}

    @classmethod
    def register(cls, name, inp_type):
        def decorator(registered_class):
            cls._classes[name] = (inp_type, registered_class)
            return registered_class

        return decorator

    @classmethod
    def get_all_classes(cls) -> dict[str, tuple[type[AgentParams], type[AgentBenchmark[Any, Any]]]]:
        return cls._classes


class EvaluatorRegistry:
    _classes: dict[str, type[Evaluator]] = {}

    @classmethod
    def register(cls, name):
        def decorator(registered_class):
            cls._classes[name] = registered_class
            return registered_class

        return decorator

    @classmethod
    def get_all_classes(cls) -> dict[str, type[Evaluator]]:
        return cls._classes
