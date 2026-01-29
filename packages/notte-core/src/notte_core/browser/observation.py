import base64
import io
from base64 import b64decode, b64encode
from datetime import datetime
from io import BytesIO
from textwrap import dedent
from typing import Annotated, Any

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing_extensions import override

from notte_core.actions import ActionUnion
from notte_core.browser.highlighter import BoundingBox, ScreenshotHighlighter
from notte_core.browser.snapshot import BrowserSnapshot, SnapshotMetadata, ViewportData
from notte_core.common.config import ScreenshotType, config
from notte_core.data.space import DataSpace
from notte_core.errors.base import NotteBaseError
from notte_core.profiling import profiler
from notte_core.space import ActionSpace
from notte_core.utils.image import draw_text_with_rounded_background
from notte_core.utils.url import clean_url

_empty_observation_instance = None


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
            try:
                # Quick dimension check using JPEG header parsing (no full decode)
                # SOF0 marker contains dimensions
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
                        # If dimensions are even, return as-is (fast path)
                        if width % 2 == 0 and height % 2 == 0:
                            return v
                        # Need to pad - fall through to PIL path
                        break
                    # Skip to next marker
                    length = (v[pos + 2] << 8) | v[pos + 3]
                    if length < 2:  # Invalid JPEG marker length
                        break
                    pos += 2 + length
                else:
                    # Couldn't parse dimensions, fall through to PIL for safety
                    pass
            except Exception:
                # Parsing failed, fall through to PIL for safety
                pass

        # Slow path: use PIL for non-JPEG or images that need padding
        try:
            img = Image.open(io.BytesIO(v))
        except Exception:
            return Observation.empty().screenshot.raw

        orig_img = img

        # Pad to even width and height (required for video encoding)
        width, height = img.size
        new_width = width + (width % 2)
        new_height = height + (height % 2)

        if new_width != width or new_height != height:
            new_img = Image.new(
                img.mode, (new_width, new_height), (255, 255, 255) if img.mode == "RGB" else (255, 255, 255, 255)
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


class Observation(BaseModel):
    metadata: Annotated[
        SnapshotMetadata, Field(description="Metadata of the current page, i.e url, page title, snapshot timestamp.")
    ]
    screenshot: Annotated[Screenshot, Field(description="Base64 encoded screenshot of the current page", repr=False)]
    space: Annotated[ActionSpace, Field(description="Available actions in the current state")]

    @property
    def clean_url(self) -> str:
        return clean_url(self.metadata.url)

    @staticmethod
    def from_snapshot(snapshot: BrowserSnapshot, space: ActionSpace) -> "Observation":
        bboxes = [node.bbox.with_id(node.id) for node in snapshot.interaction_nodes() if node.bbox is not None]
        return Observation(
            metadata=snapshot.metadata,
            screenshot=Screenshot(raw=snapshot.screenshot, bboxes=bboxes, last_action_id=None),
            space=space,
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
                    timestamp=datetime.min,
                    viewport=ViewportData(
                        scroll_x=0, scroll_y=0, viewport_width=0, viewport_height=0, total_width=0, total_height=0
                    ),
                    tabs=[],
                ),
                screenshot=Screenshot(raw=generate_empty_picture(), bboxes=[], last_action_id=None),
                space=ActionSpace(interaction_actions=[], description=""),
            )
        return _empty_observation_instance


class ExecutionResult(BaseModel):
    # action: BaseAction
    action: ActionUnion
    success: bool
    message: str
    data: DataSpace | None = None
    exception: NotteBaseError | Exception | None = Field(default=None)

    @field_validator("exception", mode="before")
    @classmethod
    def validate_exception(cls, v: Any) -> NotteBaseError | Exception | None:
        if isinstance(v, str):
            return NotteBaseError(dev_message=v, user_message=v, agent_message=v)
        return v

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
