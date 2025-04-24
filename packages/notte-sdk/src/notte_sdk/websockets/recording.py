import asyncio
import threading
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Callable

import websockets.client
from loguru import logger
from notte_core.common.resource import SyncResource
from pydantic import BaseModel, Field, PrivateAttr
from typing_extensions import override


class JupyterKernelViewer:
    @staticmethod
    def display_image(image_data: bytes):
        from IPython.display import clear_output, display  # type: ignore
        from notte_core.utils.image import image_from_bytes

        image = image_from_bytes(image_data)
        clear_output(wait=True)
        return display(image)


class SessionRecordingWebSocket(BaseModel, SyncResource):  # type: ignore
    """WebSocket client for receiving session recording data in binary format."""

    wss_url: str
    max_frames: int = 300
    frames: list[bytes] = Field(default_factory=list)
    on_frame: Callable[[bytes], None] | None = None
    output_path: Path | None = None
    _thread: threading.Thread | None = PrivateAttr(default=None)
    _stop_event: threading.Event | None = PrivateAttr(default=None)

    def _run_async_loop(self) -> None:
        """Run the async event loop in a separate thread."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.watch())
        finally:
            loop.close()

    @override
    def start(self) -> None:
        """Start recording in a separate thread."""
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run_async_loop)
        self._thread.start()

    @override
    def stop(self) -> None:
        """Stop the recording thread."""
        if self._stop_event:
            self._stop_event.set()
        if self._thread:
            self._thread.join()
            self._thread = None
            self._stop_event = None

    async def connect(self) -> AsyncIterator[bytes]:
        """Connect to the WebSocket and yield binary recording data.

        Yields:
            Binary data chunks from the recording stream
        """
        try:
            async with websockets.client.connect(self.wss_url) as websocket:
                async for message in websocket:
                    if isinstance(message, bytes):
                        if len(self.frames) >= self.max_frames:
                            break
                        logger.debug(f"Received {len(message)} bytes")
                        self.frames.append(message)
                        yield message
                    else:
                        logger.warning(f"Received non-binary message: {message}")
        except websockets.exceptions.WebSocketException as e:
            logger.error(f"WebSocket error: {e}")
            raise

    async def watch(self) -> None:
        """Save the recording stream to a file."""
        output_path = self.output_path or Path("recording.mp4")
        output_path = Path(output_path)
        with output_path.open("wb") as f:
            async for chunk in self.connect():
                if self._stop_event and self._stop_event.is_set():
                    break
                _ = f.write(chunk)
                if self.on_frame:
                    self.on_frame(chunk)
                else:
                    _ = JupyterKernelViewer.display_image(chunk)
        logger.info(f"Recording saved to {output_path}")
