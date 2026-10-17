import asyncio

import pytest
from notte_sdk.websockets.base import WebsocketService
from websockets.asyncio.server import ServerConnection, serve


@pytest.mark.parametrize("cancel", [False, True])
def test_recording_stream_closes_its_connection(cancel: bool) -> None:
    async def exercise() -> None:
        closed = asyncio.Event()

        async def recording(connection: ServerConnection) -> None:
            await connection.send("ignore text frames")
            await connection.send(b"recording frame")
            await connection.wait_closed()
            closed.set()

        async with serve(recording, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            service = WebsocketService(wss_url=f"ws://127.0.0.1:{port}", process=lambda _: None)
            stream = service.connect()
            assert await asyncio.wait_for(anext(stream), timeout=2) == b"recording frame"
            if cancel:
                pending = asyncio.create_task(anext(stream))
                await asyncio.sleep(0)
                pending.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await pending
            else:
                await stream.aclose()
            await asyncio.wait_for(closed.wait(), timeout=2)

    with asyncio.Runner() as runner:
        runner.run(exercise())
