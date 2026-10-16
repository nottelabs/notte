"""Exercise the original demo with the native wallet SDK and an offline HTTP response."""

import asyncio
import json
import sys
from pathlib import Path

import httpx
from demo import run_demo
from link import AsyncClient


async def main() -> dict:
    fixture = json.loads((Path(__file__).parents[1] / "test-card.json").read_text())
    reject = len(sys.argv) > 1 and sys.argv[1] == "reject"
    calls = []

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET" and request.url.params.get("include") == "card"
        calls.append(True)
        if reject:
            return httpx.Response(401, json={"error": {"message": "PRIVATE_FIXTURE_BODY"}})
        return httpx.Response(200, json=fixture)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as transport:
        result = await run_demo(AsyncClient(access_token="test-link-token", http_client=transport))
    assert len(calls) == 1
    return result


if __name__ == "__main__":
    try:
        with asyncio.Runner() as runner:
            print(json.dumps(runner.run(main())))
    except Exception as error:
        print(str(error))
        raise SystemExit(1) from None
