import datetime as dt

from notte.data.space import DataSpace
from notte.llms.engine import TResponseFormat
from notte.llms.service import LLMService


class SchemaScrapingPipe:
    """
    Data scraping pipe that scrapes data from the page into a structured JSON output format
    """

    def __init__(self, llmserve: LLMService) -> None:
        self.llmserve: LLMService = llmserve

    def forward(
        self,
        url: str,
        data: DataSpace,
        response_format: type[TResponseFormat],
        instructions: str | None,
    ) -> DataSpace:
        # make LLM call
        response = self.llmserve.structured_completion(
            prompt_id="extract-json-schema/multi-entity",
            response_format=response_format,
            variables={
                "url": url,
                "schema": response_format.model_json_schema(),
                "content": data.markdown,
                "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "instructions": instructions or "no additional instructions",
            },
        )
        return DataSpace(
            markdown=data.markdown,
            images=data.images,
            structured=response,
        )
