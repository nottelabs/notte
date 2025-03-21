from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar, Self

from pydantic import BaseModel, Field, model_validator


class BenchmarkTask(BaseModel):
    registry: ClassVar[dict[str, type[BenchmarkTask]]] = {}
    path: ClassVar[str]
    exclude_path: ClassVar[str | None] = None

    question: str
    id: str
    answer: str | None = None
    url: str | None = None
    website_name: str | None = None

    def __init_subclass__(cls, **kwargs: dict[Any, Any]):
        super().__init_subclass__(**kwargs)  # type: ignore
        BenchmarkTask.registry[cls.__name__.removesuffix("Task")] = cls

    @classmethod
    def read_tasks(cls, path: Path | str | None = None, exclude_path: Path | str | None = None) -> list[Self]:
        tasks: list[Self] = []

        if path is None:
            path = Path(__file__).parent / cls.path

        if exclude_path is None and cls.exclude_path is not None:
            exclude_path = Path(__file__).parent / cls.exclude_path

        with open(path, "r") as f:
            for line in f.readlines():
                tasks.append(cls.model_validate_json(line))

        if exclude_path is not None:
            with open(exclude_path, "r") as f:
                exclude_ids: set[str] = set()
                for line in f.readlines():
                    exclude_ids.add(json.loads(line)["id"])

            return [task for task in tasks if task.id not in exclude_ids]
        return tasks


class WebVoyagerTask(BenchmarkTask):
    path: ClassVar[str] = "webvoyager/webvoyager.jsonl"
    exclude_path: ClassVar[str | None] = "webvoyager/webvoyager_excluded.jsonl"

    question: str = Field()
    id: str = Field()
    answer: str = Field()  # type: ignore[reportIncompatibleVariableOverride]
    url: str = Field()  # type: ignore[reportIncompatibleVariableOverride]
    website_name: str = Field()  # type: ignore[reportIncompatibleVariableOverride]


class WebVoyagerSimpleTask(WebVoyagerTask):
    path: ClassVar[str] = "webvoyager/webvoyager_simple.jsonl"


class WebVoyagerSingleTask(WebVoyagerTask):
    path: ClassVar[str] = "webvoyager/webvoyager_single.jsonl"


class WebVoyagerConvergence(BenchmarkTask):
    path: ClassVar[str] = "webvoyager/webvoyager_convergence.jsonl"

    question: str = Field()
    id: str = Field()
    url: str = Field()  # type: ignore[reportIncompatibleVariableOverride]
    website_name: str = Field()  # type: ignore[reportIncompatibleVariableOverride]


class ProxyTask(BenchmarkTask):
    path: ClassVar[str] = "scratch/proxy.jsonl"


class GAIATask(BenchmarkTask):
    path: ClassVar[str] = "gaia/GAIA_webvoyager.jsonl"
    question: str = Field()
    id: str = Field()
    level: int = Field()
    answer: str = Field()  # type: ignore[reportIncompatibleVariableOverride]

    @model_validator(mode="before")
    @classmethod
    def arrange_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            data["id"] = "GAIA--" + data["task_id"]
            data["level"] = data["Level"]
            data["answer"] = data["Final answer"]
            data["question"] = data["quest"]

        return data  # type: ignore[reportUnknownVariableType]
