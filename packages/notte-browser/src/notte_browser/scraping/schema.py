import datetime as dt

from litellm import json
from loguru import logger
from notte_core.data.space import DictBaseModel, NoStructuredData, StructuredData
from notte_core.llms.engine import TResponseFormat
from notte_core.llms.service import LLMService
from pydantic import BaseModel

from notte_browser.scraping.pruning import MarkdownPruningPipe


class _Hotel(BaseModel):
    city: str
    price: int
    currency: str
    availability: str
    return_date: str
    link: str


class _Hotels(BaseModel):
    hotels: list[_Hotel]


class SchemaScrapingPipe:
    """
    Data scraping pipe that scrapes data from the page into a structured JSON output format
    """

    def __init__(self, llmserve: LLMService) -> None:
        self.llmserve: LLMService = llmserve

    @staticmethod
    def success_example() -> StructuredData[_Hotels]:
        return StructuredData(
            success=True,
            data=_Hotels.model_validate(
                {
                    "hotels": [
                        {
                            "city": "Edinburg",
                            "price": 100,
                            "currency": "USD",
                            "availability": "2024-12-28",
                            "return_date": "2024-12-30",
                            "link": "https://www.example.com/edinburg-hotel-1",
                        },
                        {
                            "city": "Edinburg",
                            "price": 120,
                            "currency": "USD",
                            "availability": "2024-12-28",
                            "return_date": "2024-12-30",
                            "link": "https://www.example.com/edinburg-hotel-2",
                        },
                    ]
                }
            ),
        )

    @staticmethod
    def failure_example() -> StructuredData[NoStructuredData]:
        return StructuredData(
            success=False, error="The user requested information about a cat but the document is about a dog", data=None
        )

    async def forward(
        self,
        url: str,
        document: str,
        response_format: type[TResponseFormat] | None,
        instructions: str | None,
        verbose: bool = False,
        use_link_placeholders: bool = True,
    ) -> StructuredData[BaseModel]:
        # make LLM call
        # TODO: add masking but needs more testing
        masked_document = MarkdownPruningPipe.mask(document)
        document = self.llmserve.clip_tokens(masked_document.content if use_link_placeholders else document)
        match (response_format, instructions):
            case (None, None):
                raise ValueError("response_format and instructions cannot be both None")
            case (None, _):
                structured = await self.llmserve.structured_completion(
                    prompt_id="extract-without-json-schema",
                    variables={
                        "document": document,
                        "instructions": instructions,
                        "success_example": self.success_example().model_dump_json(),
                        "failure_example": self.failure_example().model_dump_json(),
                        "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    },
                    response_format=StructuredData[DictBaseModel],
                    use_strict_response_format=False,
                )
                if verbose:
                    logger.trace(f"LLM Structured Response with no schema:\n{structured}")
                return structured
            case (_response_format, _):
                assert _response_format is not None

                response: StructuredData[DictBaseModel] = await self.llmserve.structured_completion(
                    prompt_id="extract-json-schema/multi-entity",
                    response_format=StructuredData[DictBaseModel],
                    use_strict_response_format=False,
                    variables={
                        "url": url,
                        "failure_example": StructuredData(
                            success=False,
                            error="<REASONING ABOUT WHY YOU CANNOT ANSWER THE USER REQUEST>",
                            data=None,
                        ).model_dump_json(),
                        "success_example": self.success_example().model_dump_json(),
                        "schema": json.dumps(StructuredData[_response_format].model_json_schema()),
                        "content": document,
                        "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "instructions": instructions,
                    },
                )
                if verbose:
                    logger.trace(f"LLM Structured Response with user provided schema:\n{response}")
                # try model_validate
                if not response.success or response.data is None:
                    return response
                try:
                    if isinstance(response.data.root, list):
                        return StructuredData(
                            success=False,
                            error="The response is a list, but the schema is not a list",
                            data=response.data,
                        )
                    data: BaseModel = _response_format.model_validate(response.data.root)
                    if use_link_placeholders:
                        data = MarkdownPruningPipe.unmask_pydantic(document=masked_document, data=data)
                    return StructuredData[BaseModel](
                        success=response.success,
                        error=response.error,
                        data=data,
                    )
                except Exception as e:
                    if verbose:
                        logger.trace(
                            (
                                "LLM Response cannot be validated into the provided"
                                f" schema:\n{_response_format.model_json_schema()}"
                            )
                        )
                    data = response.data
                    if use_link_placeholders:
                        data = MarkdownPruningPipe.unmask_pydantic(document=masked_document, data=data)
                    return StructuredData(
                        success=False,
                        error=f"Cannot validate response into the provided schema. Error: {e}",
                        data=data,
                    )
