import base64
import datetime as dt
import io
from base64 import b64decode, b64encode
from collections.abc import Iterator
from contextlib import contextmanager
from io import BytesIO
from textwrap import dedent
from typing import Annotated, Any

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing_extensions import override

from notte_core.actions import ActionUnion
from notte_core.browser.highlighter import BoundingBox, ScreenshotHighlighter
from notte_core.browser.snapshot import BrowserSnapshot, SnapshotMetadata, ViewportData
from notte_core.common.config import ScreenshotType, config
from notte_core.common.logging import logger
from notte_core.data.space import DataSpace
from notte_core.errors.base import NotteBaseError
from notte_core.profiling import profiler
from notte_core.space import ActionSpace
from notte_core.utils.image import draw_text_with_rounded_background
from notte_core.utils.url import clean_url

_empty_observation_instance = None


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class TimedSpan(BaseModel):
    started_at: dt.datetime
    ended_at: dt.datetime | None

    @model_validator(mode="after")
    def validate_order(self) -> "TimedSpan":
        if self.ended_at is not None and self.started_at > self.ended_at:
            raise ValueError("started_at must be <= ended_at")
        return self

    @staticmethod
    def start() -> "TimedSpan":
        return TimedSpan(started_at=utc_now(), ended_at=None)

    def close(self) -> "FilledTimedSpan":
        if self.ended_at is None:
            self.ended_at = utc_now()
        return FilledTimedSpan(started_at=self.started_at, ended_at=self.ended_at)

    def as_fields(self) -> dict[str, dt.datetime]:
        return {
            "started_at": self.started_at,
            "ended_at": self.ended_at or utc_now(),
        }

    @staticmethod
    def empty() -> "FilledTimedSpan":
        with TimedSpan.capture() as span:
            pass
        return span.close()

    @staticmethod
    @contextmanager
    def capture() -> Iterator["TimedSpan"]:
        span = TimedSpan.start()
        try:
            yield span
        finally:
            _ = span.close()


class FilledTimedSpan(BaseModel):
    started_at: dt.datetime
    ended_at: dt.datetime


class Screenshot(BaseModel):
    raw: bytes = Field(repr=False)
    bboxes: list[BoundingBox] = Field(default_factory=list)
    last_action_id: str | None = None

    model_config = {  # type: ignore[reportUnknownMemberType]
        "json_encoders": {
            bytes: lambda v: b64encode(v).decode("utf-8") if v else None,
        }
    }

    @field_validator("raw", mode="before")
    @classmethod
    def validate_raw(cls, v: bytes | str) -> bytes:
        if isinstance(v, str):
            v = b64decode(v)

        # replace with empty obs in case of failure
        if not v:
            return Observation.empty().screenshot.raw

        # Fast path: check JPEG magic bytes (FFD8) - most common case from CDP screenshots
        # This avoids sync PIL operations for valid JPEG images
        if len(v) >= 2 and v[0:2] == b"\xff\xd8":
            # Valid JPEG, check if dimensions are even (required for video encoding)
            # Only use PIL if we need to pad - this is rare
            # Quick dimension check using JPEG header parsing (no full decode).
            # Every index is guarded by the loop bound, so malformed input
            # falls through to Pillow without an exception-based control path.
            pos = 2
            while pos < len(v) - 9:
                if v[pos] != 0xFF:
                    break
                marker = v[pos + 1]
                # SOF markers (0xC0-0xCF except 0xC4, 0xC8, 0xCC)
                if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    if pos + 8 >= len(v):  # Ensure we can read height and width
                        break
                    height = (v[pos + 5] << 8) | v[pos + 6]
                    width = (v[pos + 7] << 8) | v[pos + 8]
                    # If dimensions are even and the image has its end marker,
                    # return as-is without forcing a full synchronous decode.
                    if width % 2 == 0 and height % 2 == 0 and v.endswith(b"\xff\xd9"):
                        return v
                    # Need to pad - fall through to PIL path
                    break
                # Skip to next marker
                length = (v[pos + 2] << 8) | v[pos + 3]
                if length < 2:  # Invalid JPEG marker length
                    break
                pos += 2 + length

        # Slow path: use PIL for non-JPEG or images that need padding
        try:
            img = Image.open(io.BytesIO(v))
            # Image.open is lazy. Force decoding here so a truncated image
            # cannot escape validation and fail later in display or replay code.
            _ = img.load()  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            orig_img = img

            # Pad to even width and height (required for video encoding)
            width, height = img.size
            new_width = width + (width % 2)
            new_height = height + (height % 2)

            if new_width != width or new_height != height:
                new_img = Image.new(
                    img.mode,
                    (new_width, new_height),
                    (255, 255, 255) if img.mode == "RGB" else (255, 255, 255, 255),
                )
                new_img.paste(img, (0, 0))
                img = new_img

            if img is orig_img and img.format == "JPEG":
                return v

            buffer = io.BytesIO()
            # Convert to RGB if necessary (PNG with transparency needs this)
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGB")

            img.save(buffer, format="JPEG", quality=85)
            _ = buffer.seek(0)
            return buffer.getvalue()
        except OSError:
            logger.opt(exception=True).debug("Failed to decode screenshot data; using an empty screenshot")
            return Observation.empty().screenshot.raw

    @override
    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        data = super().model_dump(*args, **kwargs)
        data["raw"] = b64encode(self.raw).decode("utf-8")
        return data

    @profiler.profiled(service_name="observation")
    def bytes(self, type: ScreenshotType | None = None, text: str | None = None) -> bytes:
        def _bytes():
            nonlocal type
            type = type or ("full" if config.highlight_elements else "raw")
            # config.highlight_elements
            match type:
                case "raw":
                    return self.raw
                case "full":
                    if len(self.bboxes) > 0:
                        return ScreenshotHighlighter.forward(self.raw, self.bboxes)
                    return self.raw
                case "last_action":
                    bboxes = [bbox for bbox in self.bboxes if bbox.notte_id == self.last_action_id]

                    if self.last_action_id is None or len(bboxes) == 0:
                        return self.raw
                    return ScreenshotHighlighter.forward(self.raw, bboxes)
                case _:  # pyright: ignore[reportUnnecessaryComparison]
                    raise ValueError(f"Invalid screenshot type: {type}")  # pyright: ignore[reportUnreachable]

        img_bytes = _bytes()

        if text is None:
            return img_bytes

        img = Image.open(io.BytesIO(img_bytes))
        width, height = img.size
        min_len = max(min(width, height), 25)
        font_size = min_len // 25

        # Use the modular function to draw text with rounded background (with emoji support)
        draw_text_with_rounded_background(
            img=img,
            text=text,
            position=(width // 2, 4 * height // 5),
            font=None,  # Will use emoji-capable font automatically
            text_color="white",
            bg_color=(0, 0, 0, 166),  # Black with 65% opacity
            padding=10,
            corner_radius=12,
            anchor="mm",
            max_width=30,
            font_size=font_size,
        )

        buffer = io.BytesIO()
        img = img.convert("RGB")
        img.save(
            buffer,
            "JPEG",
        )
        _ = buffer.seek(0)
        return buffer.getvalue()

    def display(self, type: ScreenshotType | None = None) -> "Image.Image | None":
        from notte_core.utils.image import image_from_bytes

        data = self.bytes(type)
        return image_from_bytes(data)


class TrajectoryProgress(BaseModel):
    current_step: int
    max_steps: int


class Observation(FilledTimedSpan):
    metadata: Annotated[
        SnapshotMetadata, Field(description="Metadata of the current page, i.e url, page title, snapshot timestamp.")
    ]
    screenshot: Annotated[Screenshot, Field(description="Base64 encoded screenshot of the current page", repr=False)]
    space: Annotated[ActionSpace, Field(description="Available actions in the current state")]

    @property
    def clean_url(self) -> str:
        return clean_url(self.metadata.url)

    @staticmethod
    def from_snapshot(snapshot: BrowserSnapshot, space: ActionSpace, span: FilledTimedSpan) -> "Observation":
        bboxes = [node.bbox.with_id(node.id) for node in snapshot.interaction_nodes() if node.bbox is not None]
        return Observation(
            metadata=snapshot.metadata,
            screenshot=Screenshot(raw=snapshot.screenshot, bboxes=bboxes, last_action_id=None),
            space=space,
            started_at=span.started_at,
            ended_at=span.ended_at,
        )

    @field_validator("screenshot", mode="before")
    @classmethod
    def validate_screenshot(cls, v: Screenshot | bytes | str) -> Screenshot:
        if isinstance(v, str):
            v = base64.b64decode(v)
        if isinstance(v, bytes):
            return Screenshot(raw=v, bboxes=[], last_action_id=None)
        return v

    @staticmethod
    def empty() -> "Observation":
        def generate_empty_picture(width: int = 1280, height: int = 1080) -> bytes:
            # Create a small image with "Empty Observation" text
            img = Image.new("RGB", (width, height), color="white")
            draw = ImageDraw.Draw(img)

            text = dedent(
                """[Empty observation]
                Use Goto action to start navigating"""
            )

            medium_font = ImageFont.load_default(size=30)
            draw.text((width // 2, height // 2), text, fill="black", anchor="mm", align="center", font=medium_font)

            # Convert to bytes
            buffer = BytesIO()
            img.save(buffer, format="JPEG")
            empty_screenshot_data = buffer.getvalue()
            return empty_screenshot_data

        global _empty_observation_instance

        if _empty_observation_instance is None:
            # Create a minimal 1x1 pixel transparent PNG as empty screenshot
            # Create a regular Observation instance with empty values
            _empty_observation_instance = Observation(
                metadata=SnapshotMetadata(
                    url="",
                    title="",
                    timestamp=dt.datetime.min.replace(tzinfo=dt.timezone.utc),
                    viewport=ViewportData(
                        scroll_x=0, scroll_y=0, viewport_width=0, viewport_height=0, total_width=0, total_height=0
                    ),
                    tabs=[],
                ),
                screenshot=Screenshot(raw=generate_empty_picture(), bboxes=[], last_action_id=None),
                space=ActionSpace(interaction_actions=[], description=""),
                started_at=utc_now(),
                ended_at=utc_now(),
            )

        return _empty_observation_instance


class SerializedError(BaseModel):
    """Lossless wire representation of an `ExecutionResult.exception`.

    The legacy `exception` field is serialized as `str(e)`, which collapses the error
    to whichever single message the server's `ErrorConfig` mode baked in and drops the
    concrete type and the retry/notify flags. This model carries all of it so clients
    can rehydrate the exception the server actually raised. The field is additive for
    wire compatibility: old servers never send it, old clients ignore it.
    """

    error_type: str
    dev_message: str
    user_message: str
    agent_message: str
    should_retry_later: bool = False
    should_notify_team: bool = False

    @staticmethod
    def from_exception(e: Exception) -> "SerializedError":
        if isinstance(e, NotteBaseError):
            return SerializedError(
                error_type=type(e).__name__,
                dev_message=e.dev_message,
                user_message=e.user_message,
                agent_message=e.agent_message,
                should_retry_later=e.should_retry_later,
                should_notify_team=e.should_notify_team,
            )
        message = str(e)
        return SerializedError(
            error_type=type(e).__name__,
            dev_message=message,
            user_message=message,
            agent_message=message,
        )

    def to_exception(self) -> NotteBaseError:
        error_cls = self._resolve_error_class()
        error = error_cls.__new__(error_cls)
        # Subclass __init__ signatures differ (e.g. ActionExecutionError takes
        # action_id/url/reason), so rebuild through the uniform base initializer.
        NotteBaseError.__init__(
            error,
            dev_message=self.dev_message,
            user_message=self.user_message,
            agent_message=self.agent_message,
            should_retry_later=self.should_retry_later,
            should_notify_team=self.should_notify_team,
        )
        return error

    def _resolve_error_class(self) -> type[NotteBaseError]:
        # Imported lazily so every notte-core error subclass is registered in
        # `__subclasses__` before the walk, without import cycles at module load.
        import notte_core.errors.actions  # noqa: F401  # pyright: ignore[reportUnusedImport]
        import notte_core.errors.llm  # noqa: F401
        import notte_core.errors.processing  # noqa: F401
        import notte_core.errors.provider  # noqa: F401
        import notte_core.errors.validation  # noqa: F401

        # Errors defined outside notte-core (or not imported in this process)
        # rehydrate as the base class: the type is best-effort, the messages and
        # flags are not.
        candidates: list[type[NotteBaseError]] = [NotteBaseError]
        while candidates:
            cls = candidates.pop()
            if cls.__name__ == self.error_type:
                return cls
            candidates.extend(cls.__subclasses__())
        return NotteBaseError


class ExecutionResult(FilledTimedSpan):
    # action: BaseAction
    action: ActionUnion
    success: bool
    message: str
    data: DataSpace | None = None
    exception: NotteBaseError | Exception | None = Field(default=None)
    exception_detail: SerializedError | None = None

    @field_validator("exception", mode="before")
    @classmethod
    def validate_exception(cls, v: Any) -> NotteBaseError | Exception | None:
        if isinstance(v, str):
            return NotteBaseError(dev_message=v, user_message=v, agent_message=v)
        return v

    @model_validator(mode="after")
    def sync_exception_detail(self) -> "ExecutionResult":
        if self.success:
            return self
        if self.exception is None:
            if self.exception_detail is not None:
                # Wire payload from a server that only sets the structured field.
                self.exception = self.exception_detail.to_exception()
        elif self.exception_detail is None:
            self.exception_detail = SerializedError.from_exception(self.exception)
        elif type(self.exception) is NotteBaseError:
            # The legacy string field was rehydrated as a bare NotteBaseError by
            # `validate_exception`; the detail knows the real type, messages and flags.
            self.exception = self.exception_detail.to_exception()
        return self

    model_config: ConfigDict = ConfigDict(  # pyright: ignore [reportIncompatibleVariableOverride]
        arbitrary_types_allowed=True,
        json_encoders={
            Exception: lambda e: str(e),
        },
    )

    @override
    def model_post_init(self, context: Any, /) -> None:
        if self.success:
            if self.exception is not None:
                raise ValueError("Exception should be None if success is True")
