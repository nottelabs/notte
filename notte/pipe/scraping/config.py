from enum import StrEnum

from pydantic import BaseModel

from notte.pipe.rendering.pipe import DomNodeRenderingConfig, DomNodeRenderingType
from notte.sdk.types import ScrapeRequest


class ScrapingType(StrEnum):
    SIMPLE = "simple"
    COMPLEX = "complex"


class ScrapingConfig(BaseModel):
    type: ScrapingType = ScrapingType.SIMPLE
    rendering: DomNodeRenderingConfig = DomNodeRenderingConfig(
        type=DomNodeRenderingType.MARKDOWN,
        include_ids=False,
        include_text=True,
    )
    request: ScrapeRequest = ScrapeRequest()

    def __post_init__(self):
        # override rendering config based on request
        self.rendering.include_images = self.request.scrape_images
        self.rendering.include_links = self.request.scrape_links
