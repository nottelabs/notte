import datetime as dt
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import requests

from notte.actions.space import ActionSpace
from notte.browser.node_type import clean_url
from notte.browser.snapshot import BrowserSnapshot

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore


class ImageCategory(Enum):
    ICON = "icon"
    CONTENT_IMAGE = "content_image"
    DECORATIVE = "decorative"
    SVG_ICON = "svg_icon"
    SVG_CONTENT = "svg_content"


@dataclass
class ImageData:
    id: str
    url: str | None = None
    category: ImageCategory | None = None

    def bytes(self) -> bytes:
        if self.url is None:
            raise ValueError("Image URL is not available")
        return requests.get(self.url).content


@dataclass
class DataSpace:
    markdown: str | None = None
    images: list[ImageData] | None = None
    structured: list[dict[str, Any]] | None = None


@dataclass
class Observation:
    title: str
    url: str
    timestamp: dt.datetime = field(default_factory=dt.datetime.now)
    screenshot: bytes | None = None
    _space: ActionSpace | None = None
    data: DataSpace | None = None

    @property
    def clean_url(self) -> str:
        return clean_url(self.url)

    @property
    def space(self) -> ActionSpace:
        if self._space is None:
            raise ValueError("Space is not available for this observation")
        return self._space

    @space.setter
    def space(self, space: ActionSpace) -> None:
        self._space = space

    def has_space(self) -> bool:
        return self._space is not None

    def has_data(self) -> bool:
        return self.data is not None

    def display_screenshot(self) -> "Image.Image | None":
        from notte.utils.image import image_from_bytes

        if self.screenshot is None:
            return None
        return image_from_bytes(self.screenshot)

    @staticmethod
    def from_snapshot(
        snapshot: BrowserSnapshot, space: ActionSpace | None = None, data: DataSpace | None = None
    ) -> "Observation":
        return Observation(
            title=snapshot.title,
            url=snapshot.url,
            timestamp=snapshot.timestamp,
            screenshot=snapshot.screenshot,
            _space=space,
            data=data,
        )
