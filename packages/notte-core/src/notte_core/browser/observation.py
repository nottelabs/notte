from base64 import b64encode
from typing import Annotated, Any

from notte_browser.dom.highlighter import ScreenshotHighlighter
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import override

from notte_core.browser.snapshot import BrowserSnapshot, SnapshotMetadata
from notte_core.common.config import config
from notte_core.data.space import DataSpace
from notte_core.errors.base import NotteBaseError
from notte_core.space import ActionSpace
from notte_core.utils.url import clean_url


class TrajectoryProgress(BaseModel):
    current_step: int
    max_steps: int


class Observation(BaseModel):
    metadata: Annotated[
        SnapshotMetadata, Field(description="Metadata of the current page, i.e url, page title, snapshot timestamp.")
    ]
    screenshot: Annotated[
        bytes | None, Field(description="Base64 encoded screenshot of the current page", repr=False)
    ] = None
    screenshot_highlighted: Annotated[bytes | None, Field(description="Screenshot with highlights", repr=False)] = None
    space: Annotated[ActionSpace, Field(description="Available actions in the current state")]
    progress: Annotated[
        TrajectoryProgress | None, Field(description="Progress of the current trajectory (i.e number of steps)")
    ] = None

    model_config = {  # type: ignore[reportUnknownMemberType]
        "json_encoders": {
            bytes: lambda v: b64encode(v).decode("utf-8") if v else None,
        }
    }

    @override
    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        data = super().model_dump(*args, **kwargs)
        if self.screenshot is not None:
            data["screenshot"] = b64encode(self.screenshot).decode("utf-8")
        if self.screenshot_highlighted is not None:
            data["screenshot_highlighted"] = b64encode(self.screenshot_highlighted).decode("utf-8")
        return data

    @property
    def clean_url(self) -> str:
        return clean_url(self.metadata.url)


    def display_screenshot(self, highlighted: bool = False) -> "Image.Image | None":
        from notte_core.utils.image import image_from_bytes

        screenshot = self.screenshot_highlighted if highlighted else self.screenshot
        if screenshot is None:
            return None
        return image_from_bytes(screenshot)

    @staticmethod
    def from_snapshot(
        snapshot: BrowserSnapshot,
        space: ActionSpace,
        progress: TrajectoryProgress | None = None,
    ) -> "Observation":
        if snapshot.screenshot is None or not config.highlight_elements:
            screenshot_highlighted = None
        else:
            bboxes = [node.bbox.with_id(node.id) for node in snapshot.interaction_nodes() if node.bbox is not None]
            screenshot_highlighted = ScreenshotHighlighter.forward(
                screenshot=snapshot.screenshot, bounding_boxes=bboxes
            )
        return Observation(
            metadata=snapshot.metadata,
            screenshot=snapshot.screenshot,
            screenshot_highlighted=screenshot_highlighted,
            space=space,
            progress=progress,
        )


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
