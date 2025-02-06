from enum import Enum
from typing import Annotated, Any

import requests
from pydantic import BaseModel, Field

from notte.errors.processing import InvalidInternalCheckError


class ImageCategory(Enum):
    ICON = "icon"
    CONTENT_IMAGE = "content_image"
    DECORATIVE = "decorative"
    SVG_ICON = "svg_icon"
    SVG_CONTENT = "svg_content"


class ImageData(BaseModel):
    id: Annotated[str, Field(description="Unique identifier for the image")]
    url: Annotated[str | None, Field(description="URL of the image")] = None
    category: Annotated[ImageCategory | None, Field(description="Category of the image (icon, svg, content, etc.)")] = (
        None
    )

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


class DataSpace(BaseModel):
    markdown: Annotated[str | None, Field(description="Markdown representation of the extracted data")] = None
    images: Annotated[
        list[ImageData] | None, Field(description="List of images extracted from the page (ID and download link)")
    ] = None
    structured: Annotated[
        list[dict[str, Any]] | None, Field(description="Structured data extracted from the page in JSON format")
    ] = None
