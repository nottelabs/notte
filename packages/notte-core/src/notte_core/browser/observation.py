import base64
from base64 import b64encode
from typing import Annotated, Any

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing_extensions import override

from notte_core.browser.highlighter import BoundingBox, ScreenshotHighlighter
from notte_core.browser.snapshot import BrowserSnapshot, SnapshotMetadata
from notte_core.common.config import ScreenshotType, config
from notte_core.data.space import DataSpace
from notte_core.errors.base import NotteBaseError
from notte_core.space import ActionSpace
from notte_core.utils.url import clean_url


class TrajectoryProgress(BaseModel):
    current_step: int
    max_steps: int


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
                return ScreenshotHighlighter.forward(self.raw, self.bboxes)
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


class Observation(BaseModel):
    metadata: Annotated[
        SnapshotMetadata, Field(description="Metadata of the current page, i.e url, page title, snapshot timestamp.")
    ]
    screenshot: Annotated[Screenshot, Field(description="Base64 encoded screenshot of the current page", repr=False)]
    space: Annotated[ActionSpace, Field(description="Available actions in the current state")]
    progress: Annotated[
        TrajectoryProgress | None, Field(description="Progress of the current trajectory (i.e number of steps)")
    ] = None

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
            progress=None,
        )

    @field_validator("screenshot", mode="before")
    @classmethod
    def validate_screenshot(cls, v: Screenshot | bytes | str) -> Screenshot:
        if isinstance(v, str):
            v = base64.b64decode(v)
        if isinstance(v, bytes):
            return Screenshot(raw=v, bboxes=[], last_action_id=None)
        return v


class StepResult(BaseModel):
    success: bool
    message: str
    data: DataSpace | None = None
    exception: NotteBaseError | Exception | None = None

    model_config: ConfigDict = ConfigDict(arbitrary_types_allowed=True)  # type: ignore[reportUnknownMemberType]

    @override
    def model_post_init(self, context: Any, /) -> None:
        if self.success:
            if self.exception is not None:
                raise ValueError("Exception should be None if success is True")
