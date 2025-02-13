import datetime as dt

from loguru import logger
from pydantic import BaseModel

from notte.data.space import DictBaseModel, NoStructuredData, StructuredData
from notte.llms.engine import TResponseFormat
from notte.llms.service import LLMService


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

    def clip_tokens(self, document: str, max_tokens: int) -> str:
        tokens = self.llmserve.tokenizer.encode(document)
        if len(tokens) > max_tokens:
            logger.info(f"Cannot process document, exceeds max tokens: {len(tokens)} > {max_tokens}. Clipping...")
            return self.llmserve.tokenizer.decode(tokens[:max_tokens])
        return document

    def forward(
        self,
        url: str,
        document: str,
        response_format: type[TResponseFormat] | None,
        instructions: str | None,
        max_tokens: int,
    ) -> StructuredData[BaseModel]:
        # make LLM call
        document = self.clip_tokens(document, max_tokens)
        match (response_format, instructions):
            case (None, None):
                raise ValueError("response_format and instructions cannot be both None")
            case (None, _):
                structured = self.llmserve.structured_completion(
                    prompt_id="extract-without-json-schema",
                    variables={
                        "document": document,
                        "instructions": instructions,
                        "success_example": self.success_example().model_dump_json(),
                        "failure_example": self.failure_example().model_dump_json(),
                        "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    },
                    response_format=StructuredData[DictBaseModel],
                )
                logger.info(f"LLM Structured Response with no schema:\n{structured}")
                return structured
            case (_response_format, _):
                assert _response_format is not None
                response: BaseModel = self.llmserve.structured_completion(
                    prompt_id="extract-json-schema/multi-entity",
                    response_format=_response_format,
                    variables={
                        "url": url,
                        "schema": _response_format.model_json_schema(),
                        "content": document,
                        "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "instructions": instructions or "no additional instructions",
                    },
                )
                logger.info(f"LLM Structured Response with user provided schema:\n{response}")
                return StructuredData[BaseModel](
                    success=True,
                    error=None,
                    data=response,
                )
        raise ValueError("Invalid response format or instructions")
