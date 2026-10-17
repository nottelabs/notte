import asyncio
import json
import unittest
from urllib.parse import urlsplit

import requests
from bridge import cdp_bridge
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosedError, InvalidStatus

VERSION = {
    "product": "Chrome/150.0.0.0",
    "protocolVersion": "1.3",
    "userAgent": "test",
    "jsVersion": "1",
    "revision": "@test",
}


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.connections = set()

        async def cdp(socket):
            self.connections.add(socket)
            try:
                async for frame in socket:
                    message = json.loads(frame)
                    if message["method"] == "Test.disconnect":
                        await socket.close(1011, "test failure")
                        break
                    result = (
                        VERSION
                        if message["method"] == "Browser.getVersion"
                        else {"targetInfos": [{"targetId": "page1", "type": "page", "url": "about:blank", "title": ""}]}
                    )
                    await socket.send(json.dumps({"id": message["id"], "result": result}))
            finally:
                self.connections.remove(socket)

        self.server = await serve(cdp, "127.0.0.1", 0)
        self.cdp_url = f"ws://127.0.0.1:{self.server.sockets[0].getsockname()[1]}/?token=test-only"

    async def asyncTearDown(self):
        self.server.close()
        await self.server.wait_closed()

    async def get(self, address, path="/json/version", **kwargs):
        return await asyncio.to_thread(requests.get, f"http://{address}{path}", timeout=3, **kwargs)

    async def test_discovery_forwarding_and_cleanup(self):
        async with cdp_bridge(self.cdp_url) as address:
            metadata = (await self.get(address)).json()
            self.assertEqual(metadata["Browser"], VERSION["product"])
            self.assertFalse(self.cdp_url in str(metadata), "Discovery must hide the authenticated endpoint")
            self.assertEqual((await self.get(address, "/json/list")).json()[0]["id"], "page1")
            endpoint = metadata["webSocketDebuggerUrl"]
            self.assertEqual(urlsplit(endpoint).hostname, "127.0.0.1")
            socket = await connect(endpoint)
            await socket.send(json.dumps({"id": 3, "method": "Browser.getVersion"}))
            reply = json.loads(await asyncio.wait_for(socket.recv(), 3))
            self.assertEqual(reply["result"], VERSION)
        await asyncio.wait_for(socket.wait_closed(), 3)
        with self.assertRaises(requests.ConnectionError):
            await self.get(address)
        for attempt in range(100):
            if not self.connections:
                break
            await asyncio.sleep(0.01)
        self.assertFalse(self.connections, "Upstream sockets must close with the bridge")

    async def test_rejects_untrusted_hosts_origins_and_paths(self):
        async with cdp_bridge(self.cdp_url) as address:
            self.assertEqual((await self.get(address, headers={"Host": "untrusted.example"})).status_code, 403)
            self.assertEqual(
                (await self.get(address, headers={"Origin": "https://untrusted.example"})).status_code, 403
            )
            endpoint = (await self.get(address)).json()["webSocketDebuggerUrl"]
            for url, kwargs, expected in [
                (f"ws://{address}/wrong", {}, 404),
                (endpoint, {"origin": "https://untrusted.example"}, 403),
            ]:
                with self.assertRaises(InvalidStatus) as rejected:
                    async with connect(url, **kwargs):
                        pass
                self.assertEqual(rejected.exception.response.status_code, expected)

    async def test_forwarding_failure_closes_with_sanitized_reason(self):
        async with cdp_bridge(self.cdp_url) as address:
            endpoint = (await self.get(address)).json()["webSocketDebuggerUrl"]
            async with connect(endpoint) as socket:
                await socket.send(json.dumps({"id": 3, "method": "Test.disconnect"}))
                with self.assertRaises(ConnectionClosedError) as closed:
                    await asyncio.wait_for(socket.recv(), 3)
                self.assertEqual(closed.exception.rcvd.code, 1011)
                self.assertEqual(closed.exception.rcvd.reason, "Hosted browser connection closed")


if __name__ == "__main__":
    unittest.main()
