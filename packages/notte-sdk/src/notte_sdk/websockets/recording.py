import asyncio
import datetime as dt
import threading
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Callable

import websockets.client
from loguru import logger
from notte_core.common.resource import SyncResource
from notte_core.utils.webp_replay import WebpReplay
from pydantic import BaseModel, Field, PrivateAttr
from typing_extensions import override

# def save_frames_to_video(frames: list[bytes], output_path: Path, fps: int = 10):
#     import numpy as np
#     import imagio
#     with imageio.get_writer('output.mp4', fps=fps) as writer:
#         for img in frames:
#             writer.append_data(np.array(img))


class JupyterKernelViewer:
    @staticmethod
    def display_image(image_data: bytes):
        from IPython.display import (
            clear_output,
            display,  # pyright: ignore [reportUnknownVariableType]
        )
        from notte_core.utils.image import image_from_bytes

        image = image_from_bytes(image_data)
        clear_output(wait=True)
        return display(image)


class CV2Viewer:
    @staticmethod
    def display_image(image_data: bytes):
        import cv2
        import numpy as np

        try:
            # Assuming chunk is a JPEG image in bytes
            nparr = np.frombuffer(image_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img is not None:
                cv2.imshow("Live Stream", img)
                # Break the loop if 'q' is pressed
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    return
        except Exception as e:
            print(f"Error displaying frame: {e}")


class SessionRecordingWebSocket(BaseModel, SyncResource):  # type: ignore
    """WebSocket client for receiving session recording data in binary format."""

    wss_url: str
    fps: int = 10
    max_frames: int = 300
    frames: list[bytes] = Field(default_factory=list)
    on_frame: Callable[[bytes], None] | None = None
    output_path: Path | None = None
    _thread: threading.Thread | None = PrivateAttr(default=None)
    _stop_event: threading.Event | None = PrivateAttr(default=None)
    _loop: asyncio.AbstractEventLoop | None = PrivateAttr(default=None)
    _ws_task: asyncio.Task | None = PrivateAttr(default=None)  # pyright: ignore [reportMissingTypeArgument]
    display_image: bool = True

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
            logger.warning(f"Unexpected exception in recording loop: {e}")
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
                logger.warning("WebSocket thread did not terminate gracefully")
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
                    if len(self.frames) >= self.max_frames:
                        break
                    self.frames.append(message)
                    yield message
                else:
                    logger.warning(f"[Session Recording] Received non-binary message: {message}")
        except websockets.exceptions.WebSocketException as e:
            logger.error(f"[Session Recording] WebSocket error: {e}")
            raise
        except asyncio.CancelledError:
            # Handle cancellation explicitly
            logger.info("[Session Recording] WebSocket connection cancelled")
            raise
        finally:
            # Clean up WebSocket connection
            if websocket and not websocket.closed:
                await websocket.close()

    async def watch(self) -> None:
        """Save the recording stream to a file."""
        output_path = self.output_path or Path(f".recordings/{dt.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}/")
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        display_cv2 = False
        if self.display_image and not WebpReplay.in_notebook():
            display_cv2 = True

        if display_cv2:
            try:
                import cv2

                cv2.namedWindow("Live Stream", cv2.WINDOW_NORMAL)
            except ImportError:
                raise ImportError("To display live feed, please install opencv-python")

        f = None
        try:
            f = output_path.open("wb")
            async for chunk in self.connect():
                if self._stop_event and self._stop_event.is_set():
                    break
                _ = f.write(chunk)
                if self.on_frame:
                    self.on_frame(chunk)
                if self.display_image:
                    if WebpReplay.in_notebook():
                        _ = JupyterKernelViewer.display_image(chunk)
                    else:
                        _ = CV2Viewer.display_image(chunk)

        except asyncio.CancelledError:
            logger.info("[Session Recording] Recording task cancelled")
        finally:
            if f:
                f.close()
            if display_cv2:
                import cv2

                cv2.destroyAllWindows()

        logger.info(f"[Session Recording] Recording saved to {output_path}")
