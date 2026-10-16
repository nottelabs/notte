"""Expose Notte's authenticated CDP connection to a local ChromeDriver."""

import asyncio
import json
import logging
import secrets
from contextlib import asynccontextmanager
from http import HTTPStatus

from websockets.asyncio.client import connect
from websockets.asyncio.server import serve


@asynccontextmanager
async def cdp_bridge(cdp_url: str):
    # Neither the discovery response nor ChromeDriver's arguments contain the key.
    logger = logging.Logger("notte.selenium.bridge")
    logger.disabled = True
    try:
        async with asyncio.timeout(30), connect(cdp_url, logger=logger, open_timeout=30) as upstream:
            results = []
            for request_id, method in enumerate(("Browser.getVersion", "Target.getTargets"), 1):
                await upstream.send(json.dumps({"id": request_id, "method": method}))
                while True:
                    response = json.loads(await upstream.recv())
                    if response.get("id") == request_id:
                        results.append(response["result"])
                        break
    except Exception:
        raise RuntimeError("Could not read the hosted browser's CDP metadata") from None
    version, targets = results
    nonce = "/devtools/browser/" + secrets.token_urlsafe(24)

    async def forward(client):
        try:
            async with connect(cdp_url, logger=logger, open_timeout=30, max_size=None) as upstream:

                async def pump(source, destination):
                    async for frame in source:
                        await destination.send(frame)

                tasks = [asyncio.create_task(pump(client, upstream)), asyncio.create_task(pump(upstream, client))]
                try:
                    await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
        except Exception:
            await client.close(1011, "Hosted browser connection closed")

    async def discovery(connection, request):
        # ChromeDriver's WebSocket handshake omits the port from Host.
        if request.headers.get("Origin") or request.headers.get("Host") not in (address, "127.0.0.1"):
            return connection.respond(HTTPStatus.FORBIDDEN, "Forbidden\n")
        if request.path == nonce:
            return None
        if request.path.rstrip("/") == "/json/version":
            payload = {
                "Browser": version["product"],
                "Protocol-Version": version["protocolVersion"],
                "User-Agent": version["userAgent"],
                "V8-Version": version["jsVersion"],
                "WebKit-Version": f"537.36 ({version['revision']})",
                "webSocketDebuggerUrl": endpoint,
            }
        elif request.path.rstrip("/") in ("/json/list", "/json"):
            payload = [
                {
                    "id": x["targetId"],
                    "type": "page",
                    "title": x.get("title", ""),
                    "url": x.get("url", ""),
                    "webSocketDebuggerUrl": endpoint,
                }
                for x in targets["targetInfos"]
                if x["type"] == "page"
            ]
        else:
            return connection.respond(HTTPStatus.NOT_FOUND, "Not found\n")
        response = connection.respond(HTTPStatus.OK, json.dumps(payload))
        response.headers["Content-Type"] = "application/json"
        return response

    async with serve(
        forward, "127.0.0.1", 0, process_request=discovery, logger=logger, max_size=None, ping_interval=None
    ) as server:
        address = f"127.0.0.1:{server.sockets[0].getsockname()[1]}"
        endpoint = f"ws://{address}{nonce}"
        yield address
