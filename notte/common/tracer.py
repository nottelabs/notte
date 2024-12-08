import json
from pathlib import Path
from typing import Any, ClassVar, Protocol

from typing_extensions import override


class Tracer(Protocol):
    """Protocol for database clients that handle LLM usage logging."""

    def trace(self, *args: Any, **kwargs: Any) -> None:
        """Log LLM usage to the database."""
        pass


class LlmTracer(Tracer):

    @override
    def trace(
        self,
        timestamp: str,
        model: str,
        messages: list[dict[str, str]],
        completion: str,
        usage: dict[str, int],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log LLM usage to the database."""
        raise NotImplementedError


class LlmFileTracer(LlmTracer):

    file_path: ClassVar[Path] = Path(__file__).parent.parent.parent / "llm_usage.jsonl"

    @override
    def trace(
        self,
        timestamp: str,
        model: str,
        messages: list[dict[str, str]],
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
