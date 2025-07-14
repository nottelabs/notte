import inspect
import typing
from collections.abc import Coroutine
from datetime import datetime
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, TypeAlias

from litellm import AllMessageValues, ModelResponse  # type: ignore[import]
from loguru import logger

from notte_core.common.tracer import LlmTracer

if TYPE_CHECKING:
    pass


def strip_images_from_llm_conversation(conversation: list[AllMessageValues]) -> list[AllMessageValues]:
    stripped: list[AllMessageValues] = []

    for message in conversation:
        content = message.get("content")  # pyright: ignore [reportUnknownVariableType, reportUnknownMemberType]

        if isinstance(content, list):
            # Filter out image blocks
            new_content = [block for block in content if isinstance(block, dict) and block.get("type") != "image_url"]  # pyright: ignore [reportUnknownVariableType, reportUnknownVariableType, reportUnknownMemberType]
            stripped.append({**message, "content": new_content})  # pyright: ignore [reportArgumentType]
        else:
            # Leave string or unknown content as-is
            stripped.append(message)

    return stripped


def recover_args(func: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    sig = inspect.signature(func)
    params = list(sig.parameters.keys())

    # Map positional args to parameter names
    named_args = {}
    for param_name, arg_value in zip(params, args):
        named_args[param_name] = arg_value

    # Combine with kwargs
    all_params: dict[str, Any] = {**named_args, **kwargs}
    return all_params


ModelResponseCoroutine: TypeAlias = Coroutine[Any, Any, ModelResponse]


def trace_llm_usage(
    tracer: LlmTracer | None = None,
) -> Callable[[Callable[..., ModelResponseCoroutine]], Callable[..., ModelResponseCoroutine]]:
    def decorator(func: Callable[..., ModelResponseCoroutine]) -> Callable[..., ModelResponseCoroutine]:
        @wraps(func)
        async def wrapper(
            *args: Any,
            **kwargs: Any,
        ) -> ModelResponse:
            # Call the original function

            recovered_args = recover_args(func, args, kwargs)
            model = typing.cast(str, recovered_args.get("model"))

            messages = typing.cast(list[Any], recovered_args.get("messages"))
            response: ModelResponse = await func(*args, **kwargs)

            # Only trace if tracer is provided
            if tracer is not None:
                try:
                    _completion: str | None = response.choices[0].message.content  # type: ignore[attr-defined]
                    completion: str = _completion or ""  # type: ignore[attr-defined]

                    usage = getattr(response, "usage", None)
                    usage_dict = (
                        {
                            "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                            "completion_tokens": getattr(usage, "completion_tokens", 0),
                            "total_tokens": getattr(usage, "total_tokens", 0),
                        }
                        if usage
                        else {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                    )

                    tracer.trace(
                        timestamp=datetime.now().isoformat(),
                        model=model,
                        messages=messages,
                        completion=completion,  # type: ignore[arg-type]
                        usage=usage_dict,
                        metadata=kwargs.get("metadata"),
                    )
                except Exception as e:
                    logger.debug(f"Error logging LLM usage: {str(e)}")

            return response

        return wrapper

    return decorator
