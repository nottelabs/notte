import base64
from base64 import b64encode
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
from notte_core.space import ActionSpace
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

    @override
    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        data = super().model_dump(*args, **kwargs)
        data["raw"] = b64encode(self.raw).decode("utf-8")
        return data

    def bytes(self, type: ScreenshotType | None = None) -> bytes:
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
            img.save(buffer, format="PNG")
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
