import asyncio
import threading
from collections.abc import AsyncIterator
from typing import Any, Callable

import websockets.client
from loguru import logger
from notte_core.common.resource import SyncResource
from pydantic import BaseModel, PrivateAttr
from typing_extensions import override


class WebsocketService(BaseModel, SyncResource):  # pyright: ignore [reportUnsafeMultipleInheritance]
    """WebSocket client for receiving session recording data in binary format."""

    wss_url: str
    process: Callable[[bytes], Any]
    _thread: threading.Thread | None = PrivateAttr(default=None)
    _stop_event: threading.Event | None = PrivateAttr(default=None)
    _loop: asyncio.AbstractEventLoop | None = PrivateAttr(default=None)
    _ws_task: asyncio.Task | None = PrivateAttr(default=None)  # pyright: ignore [reportMissingTypeArgument]

    def _run_async_loop(self) -> None:
        """Run the async event loop in a separate thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            # Create a task that we can cancel
            self._ws_task = self._loop.create_task(self.watch())
            self._loop.run_until_complete(self._ws_task)  # pyright: ignore [reportUnknownMemberType, reportUnknownArgumentType]
        except asyncio.CancelledError:
            pass  # Task was cancelled, which is expected during shutdown
        except Exception as e:
            logger.debug(f"Unexpected exception in recording loop: {e}")
        finally:
            # Run all remaining tasks to completion
            pending = asyncio.all_tasks(self._loop)
            for task in pending:
                _ = task.cancel()
            if pending:
                # Allow tasks to perform cleanup
                _ = self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            self._loop.close()
            self._loop = None
            self._ws_task = None

    @override
    def start(self) -> None:
        """Start recording in a separate thread."""
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run_async_loop)
        self._thread.daemon = True  # Make it a daemon thread
        self._thread.start()

    @override
    def stop(self) -> None:
        """Stop the recording thread."""
        if self._stop_event:
            self._stop_event.set()

        if self._loop and self._ws_task and self._thread and self._thread.is_alive():  # pyright: ignore [reportUnknownMemberType]
            # Schedule task cancellation from the main thread
            _ = asyncio.run_coroutine_threadsafe(self._cancel_tasks(), self._loop)

        if self._thread:
            # Give it a reasonable timeout
            self._thread.join(timeout=5.0)
            if self._thread.is_alive():
                logger.debug("WebSocket thread did not terminate gracefully")
            self._thread = None
            self._stop_event = None

    async def _cancel_tasks(self) -> None:
        """Cancel all tasks in the event loop."""
        if self._ws_task:  # pyright: ignore [reportUnknownMemberType]
            _ = self._ws_task.cancel()  # pyright: ignore [reportUnknownMemberType]
            try:
                await self._ws_task  # pyright: ignore [reportUnknownMemberType]
            except asyncio.CancelledError:
                pass

    async def connect(self) -> AsyncIterator[bytes]:
        """Connect to the WebSocket and yield binary recording data.
        Yields:
            Binary data chunks from the recording stream
        """
        websocket = None
        try:
            websocket = await websockets.client.connect(self.wss_url)
            async for message in websocket:
                if isinstance(message, bytes):
                    yield message
                else:
                    logger.debug(f"[Session Viewer] Received non-binary message: {message}")
        except websockets.exceptions.WebSocketException as e:
            logger.debug(f"[Session Viewer] WebSocket error: {e}")
            raise
        except asyncio.CancelledError:
            # Handle cancellation explicitly
            logger.trace("[Session Viewer] WebSocket connection cancelled")
            raise
        finally:
            # Clean up WebSocket connection
            if websocket and not websocket.closed:
                await websocket.close()

    async def watch(self) -> None:
        """Display the recording stream as live images in Jupyter notebook."""

        try:
            async for chunk in self.connect():
                if self._stop_event and self._stop_event.is_set():
                    break
                _ = self.process(chunk)

        except asyncio.CancelledError:
            logger.trace("[Session Viewer] Task cancelled")
