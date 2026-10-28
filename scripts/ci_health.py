"""Independent, bounded staging and OpenRouter probes with no retries."""

from __future__ import annotations

import argparse
import json
import os
import signal
import time
from http.client import HTTPException
from pathlib import Path
from types import FrameType
from typing import TypeAlias, TypedDict, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

Json: TypeAlias = str | int | float | bool | None | list["Json"] | dict[str, "Json"]
HTTP_FAILURES = {401: "authentication", 403: "authorization", 402: "credits", 429: "capacity"}


class Result(TypedDict):
    service: str
    status: str
    http_status: int | None
    provider_status: int | None
    elapsed_seconds: float
    version: str | None


def expired(_number: int, _frame: FrameType | None) -> None:
    raise TimeoutError("Dependency request exceeded its deadline")


def read(url: str, key: str = "", payload: dict[str, Json] | None = None) -> dict[str, Json]:
    headers = {"Accept": "application/json", "User-Agent": "notte-ci-health/1.0"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=json.dumps(payload).encode() if payload is not None else None, headers=headers)
    # Socket timeouts reset for heartbeat bytes. Bound connection plus full body.
    started = time.monotonic()
    previous_handler = signal.signal(signal.SIGALRM, expired)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, 10)
    try:
        with urlopen(request, timeout=10) as response:
            body = response.read(1024 * 1024 + 1)
        if len(body) > 1024 * 1024:
            raise ValueError("Dependency response exceeded its size budget")
        value = json.loads(body)
    finally:
        _ = signal.setitimer(signal.ITIMER_REAL, 0)
        _ = signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0]:
            _ = signal.setitimer(
                signal.ITIMER_REAL, max(0.001, previous_timer[0] - (time.monotonic() - started)), previous_timer[1]
            )
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return cast(dict[str, Json], value)


def probe(service: str, key: str) -> Result:
    start = time.monotonic()
    result: Result = {
        "service": service,
        "status": "passed",
        "http_status": None,
        "provider_status": None,
        "elapsed_seconds": 0,
        "version": None,
    }
    try:
        if not key:
            result["status"] = "missing_credentials"
        elif service == "staging":
            health = read("https://us-staging.notte.cc/health")
            if not isinstance(health.get("version"), str) or not health["version"]:
                raise ValueError("Missing backend version")
            result["version"] = cast(str, health["version"])
            logs = read("https://us-staging.notte.cc/usage/logs?endpoint=sessions.start&page=1&page_size=1", key)
            if not isinstance(logs.get("items"), list):
                raise ValueError("Missing usage log page")
        elif service == "openrouter":
            completion = read(
                "https://openrouter.ai/api/v1/chat/completions",
                key,
                {
                    "model": "google/gemini-3.5-flash-lite",
                    "messages": [{"role": "user", "content": "Reply with OK."}],
                    "max_tokens": 32,
                    "provider": {"allow_fallbacks": False},
                },
            )
            error = completion.get("error")
            if isinstance(error, dict) and isinstance(error.get("code"), int):
                code = cast(int, error["code"])
                result["http_status"] = 200
                result["provider_status"] = code
                result["status"] = HTTP_FAILURES.get(code, "service_error")
            else:
                if error:
                    raise ValueError("Missing successful completion")
                choices = completion.get("choices")
                if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                    raise ValueError("Missing completion choices")
                message = choices[0].get("message")
                if (
                    not isinstance(message, dict)
                    or not isinstance(message.get("content"), str)
                    or not message["content"]
                ):
                    raise ValueError("Missing completion text")
        else:
            raise ValueError("Unknown service")
    except HTTPError as error:
        result["http_status"] = error.code
        result["status"] = HTTP_FAILURES.get(error.code, "service_error")
    except (TimeoutError, URLError, OSError, HTTPException):
        result["status"] = "transport"
    except (ValueError, TypeError):
        result["status"] = "invalid_response"
    result["elapsed_seconds"] = round(time.monotonic() - start, 3)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("service", choices=("staging", "openrouter"))
    args = parser.parse_args()
    service = cast(str, args.service)
    result = probe(service, os.environ.get("NOTTE_API_KEY" if service == "staging" else "OPENROUTER_API_KEY", ""))
    output = Path(".test-artifacts/ci-health")
    output.mkdir(parents=True, exist_ok=True)
    _ = (output / f"{service}.json").write_text(json.dumps(result, sort_keys=True) + "\n")
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as summary:
        _ = summary.write(f"## {service} dependency health\n\n```json\n{json.dumps(result, indent=2)}\n```\n")
    print(json.dumps(result))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
