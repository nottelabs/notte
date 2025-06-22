from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, ClassVar, Protocol

from litellm import AllMessageValues
from pydantic import BaseModel, Field
from typing_extensions import override


class Tracer(Protocol):
    """Protocol for database clients that handle LLM usage logging."""

    def trace(self, *args: Any, **kwargs: Any) -> None:
        """Log some usage to a local file or external service."""
        pass


ROOT_DIR = Path(__file__).parent.parent.parent.parent / "traces"
ROOT_DIR.mkdir(parents=True, exist_ok=True)


class LlmTracer(Tracer):
    @override
    def trace(
        self,
        timestamp: str,
        model: str,
        messages: list[AllMessageValues],
        completion: str,
        usage: dict[str, int],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log LLM usage to the database."""
        raise NotImplementedError


class LlmUsageDictTracer(LlmTracer):
    class LlmUsage(BaseModel):
        timestamp: str
        model: str
        messages: list[AllMessageValues]
        completion: str
        usage: dict[str, int]
        metadata: dict[str, Any] | None = None

    def __init__(self) -> None:
        self.usage: list[LlmUsageDictTracer.LlmUsage] = []

    @override
    def trace(
        self,
        timestamp: str,
        model: str,
        messages: list[AllMessageValues],
        completion: str,
        usage: dict[str, int],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log LLM usage to a file."""
        self.usage.append(
            LlmUsageDictTracer.LlmUsage(
                timestamp=timestamp,
                model=model,
                messages=messages,
                completion=completion,
                usage=usage,
                metadata=metadata,
            )
        )


class LlmUsageFileTracer(LlmTracer):
    file_path: ClassVar[Path] = ROOT_DIR / "llm_usage.jsonl"

    class LlmUsage(BaseModel):
        timestamp: str
        model: str
        messages: list[AllMessageValues]
        completion: str
        usage: dict[str, int]
        metadata: dict[str, Any] | None = None

    @override
    def trace(
        self,
        timestamp: str,
        model: str,
        messages: list[AllMessageValues],
        completion: str,
        usage: dict[str, int],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log LLM usage to a file."""
        with open(self.file_path, "a") as f:
            json.dump(
                {
                    "timestamp": timestamp,
                    "model": model,
                    "messages": messages,
                    "completion": completion,
                    "usage": usage,
                },
                f,
            )
            _ = f.write("\n")


class LlmParsingErrorFileTracer(Tracer):
    file_path: ClassVar[Path] = ROOT_DIR / "llm_parsing_error.jsonl"

    class LLmParsingError(BaseModel):
        timestamp: str = Field(default_factory=lambda: dt.datetime.now().isoformat())
        status: str
        pipe_name: str
        nb_retries: int
        error_msgs: list[str]

    @override
    def trace(
        self,
        status: str,
        pipe_name: str,
        nb_retries: int,
        error_msgs: list[str],
    ) -> None:
        """Log LLM parsing errors to a file."""
        with open(self.file_path, "a") as f:
            json.dump(
                LlmParsingErrorFileTracer.LLmParsingError(
                    status=status,
                    pipe_name=pipe_name,
                    nb_retries=nb_retries,
                    error_msgs=error_msgs,
                ).model_dump(),
                f,
            )
            _ = f.write("\n")
