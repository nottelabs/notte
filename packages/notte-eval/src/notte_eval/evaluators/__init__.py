import importlib
import typing
from typing import NamedTuple


def fetch_evaluator(key: str) -> type:
    """
    Import specific module based on key and return input and handler types
    """
    if key not in EVALUATORS_DICT:
        raise ValueError(f"Unknown handler key: {key}")

    handler = EVALUATORS_DICT[key]
    module = importlib.import_module(f"{__package__}.{handler.module_name}")

    return typing.cast(type, getattr(module, handler.evaluator_name))


class EvaluatorTuple(NamedTuple):
    module_name: str
    evaluator_name: str


EVALUATORS_DICT = {
    "webvoyager": EvaluatorTuple("webvoyager", "WebvoyagerEvaluator"),
}
