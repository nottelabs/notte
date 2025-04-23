import asyncio
import threading
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Callable

import websockets.client
from litellm import Field
from loguru import logger
from pydantic import BaseModel


class JupyterKernelViewer:
    @staticmethod
    def display_image(image_data: bytes):
        from IPython.display import clear_output, display  # type: ignore
        from notte_core.utils.image import image_from_bytes

        image = image_from_bytes(image_data)
        clear_output(wait=True)
        return display(image)


class SessionRecordingWebSocket(BaseModel):
    """WebSocket client for receiving session recording data in binary format."""

    wss_url: str
    max_frames: int = 20
    frames: list[bytes] = Field(default_factory=list)
    _thread: threading.Thread | None = None
    _stop_event: threading.Event | None = None

    def _run_async_loop(self, output_path: Path, on_frame: Callable[[bytes], None] | None = None) -> None:
        """Run the async event loop in a separate thread.

        Args:
            output_path: Path where to save the recording
            on_frame: Optional callback function to handle each frame
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.watch(output_path, on_frame))
        finally:
            loop.close()

    def start_recording(self, output_path: str | Path, on_frame: Callable[[bytes], None] | None = None) -> None:
        """Start recording in a separate thread.

        Args:
            output_path: Path where to save the recording
            on_frame: Optional callback function to handle each frame
        """
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run_async_loop, args=(Path(output_path), on_frame))
        self._thread.start()

    def stop_recording(self) -> None:
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

    async def watch(self, output_path: str | Path, on_frame: Callable[[bytes], None] | None = None) -> None:
        """Save the recording stream to a file.

        Args:
            output_path: Path where to save the recording
            on_frame: Optional callback function to handle each frame
        """
        output_path = Path(output_path)
        with output_path.open("wb") as f:
            async for chunk in self.connect():
                if self._stop_event and self._stop_event.is_set():
                    break
                _ = f.write(chunk)
                if on_frame:
                    on_frame(chunk)
                else:
                    _ = JupyterKernelViewer.display_image(chunk)
        logger.info(f"Recording saved to {output_path}")
