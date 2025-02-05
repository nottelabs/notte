from enum import StrEnum

from pydantic import BaseModel

from notte.pipe.rendering.pipe import DomNodeRenderingConfig, DomNodeRenderingType
from notte.sdk.types import ScrapeParams


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
    params: ScrapeParams = ScrapeParams()

    def __post_init__(self):
        # override rendering config based on request
        self.rendering.include_images = self.params.scrape_images
        self.rendering.include_links = self.params.scrape_links
