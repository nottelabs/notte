from dataclasses import dataclass
from enum import Enum
from typing import Any

import requests

from notte.errors.processing import InvalidInternalCheckError


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
            raise InvalidInternalCheckError(
                check="image URL is not available. Cannot retrieve image bytes.",
                url=self.url,
                dev_advice=(
                    "Check the `ImageData` construction process in the `DataScraping` pipeline to diagnose this issue."
                ),
            )
        return requests.get(self.url).content


@dataclass
class DataSpace:
    markdown: str | None = None
    images: list[ImageData] | None = None
    structured: list[dict[str, Any]] | None = None
