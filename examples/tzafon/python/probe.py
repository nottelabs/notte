import asyncio
import json
import sys

import httpx
from demo import run_demo
from fixture import CODE, Wire
from tzafon import AsyncLightcone


async def main() -> dict:
    wire = Wire(sys.argv[1], real_screenshot=True)
    async with httpx.AsyncClient(transport=httpx.MockTransport(wire)) as http:
        provider = AsyncLightcone(
            api_key="fixture-provider-key",  # pragma: allowlist secret
            base_url="https://lightcone.invalid",
            http_client=http,
            max_retries=0,  # pragma: allowlist secret
        )
        try:
            result = await run_demo(provider, CODE)
        except Exception:
            assert len(wire.requests) == 1
            raise
        assert len(wire.requests) == 3
        return result


try:
    with asyncio.Runner() as runner:
        print(json.dumps(runner.run(main())))
except Exception as error:
    print(str(error))
    raise SystemExit(1) from None
