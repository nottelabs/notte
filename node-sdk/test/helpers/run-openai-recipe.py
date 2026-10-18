"""Keep provider failures useful without exposing SDK connection details."""

import ast
import importlib.metadata
import json
import os
import re
import runpy
import socket
import sys
from importlib import import_module
from pathlib import Path
from typing import NoReturn
from unittest.mock import patch


def check_api_urls(artifact: Path) -> None:
    source = artifact.read_text()
    if artifact.suffix == ".mdx":
        source = source.split("```python notte_openai_agents.py\n", 1)[1].split("```", 1)[0]
    constructors = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "MCPServerStreamableHttp"
    ]
    assert len(constructors) == 1, "Expected the actual recipe's single MCP constructor"
    expression = compile(ast.Expression(constructors[0]), str(artifact), "eval")
    attempts: list[bool] = []

    def block_network(*_args: object, **_kwargs: object) -> NoReturn:
        attempts.append(True)
        raise AssertionError("URL construction must not open a socket")

    cases = (
        ("missing", None, "https://api.notte.cc/mcp"),
        ("empty", "", "https://api.notte.cc/mcp"),
        ("custom", "https://example.invalid", "https://example.invalid/mcp"),
        ("trailing-slash", "https://example.invalid/", "https://example.invalid/mcp"),
        ("api-prefix", "https://example.invalid/notte/", "https://example.invalid/notte/mcp"),
    )
    # Optional SDK imports also run without ambient credentials or network access.
    with (
        patch.dict(
            os.environ,
            {
                "NOTTE_API_KEY": "fixture-config-only",  # pragma: allowlist secret
                "DISABLE_TELEMETRY": "true",
                "OPENAI_AGENTS_DISABLE_TRACING": "true",
            },
            clear=True,
        ),
        patch.object(socket.socket, "connect", block_network),
        patch.object(socket.socket, "connect_ex", block_network),
        patch.object(socket, "create_connection", block_network),
    ):
        mcp = import_module("agents.mcp")
        notte = import_module("notte_sdk")
        base = import_module("notte_sdk.endpoints.base")
        pydantic = import_module("pydantic")
        namespace = {
            "os": os,
            "MCPServerStreamableHttp": mcp.MCPServerStreamableHttp,
            "create_static_tool_filter": mcp.create_static_tool_filter,
        }
        with patch.object(
            base.BaseClient, "_get_latest_pypi_version", return_value=importlib.metadata.version("notte-sdk")
        ):
            for name, value, expected in cases:
                if value is None:
                    _ = os.environ.pop("NOTTE_API_URL", None)
                else:
                    os.environ["NOTTE_API_URL"] = value
                client = notte.NotteClient()
                start = client.sessions.request_path(
                    base.NotteEndpoint(path="start", method="POST", response=pydantic.BaseModel)
                )
                server = eval(expression, namespace)
                assert start == expected.removesuffix("/mcp") + "/sessions/start", name
                assert server.params["url"] == expected, f"{name}: {server.params['url']} != {expected}"
                assert server.params["url"] == start.removesuffix("/sessions/start") + "/mcp", name
    assert not attempts, "An SDK swallowed a forbidden connection attempt"
    print(json.dumps({"cases": len(cases), "network_attempts": len(attempts)}))


if sys.argv[1:2] == ["--check-api-urls"]:
    check_api_urls(Path(sys.argv[2]))
    raise SystemExit(0)

runner, example = sys.argv[1:]
sys.argv = [runner, example]
try:
    _ = runpy.run_path(runner, run_name="__main__")
except Exception as error:
    cause = error.__context__ or error
    detail = f"{type(cause).__name__}: {cause}"
    for name, value in os.environ.items():
        if value and any(part in name.upper() for part in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
            detail = detail.replace(value, "[REDACTED]")
    detail = re.sub(r"(?:wss?|https?)://[^\s\"'<>]+", "[URL]", detail)
    print("OPENAI_DIAGNOSTIC=" + json.dumps(detail[:1200]), file=sys.stderr)
    raise
