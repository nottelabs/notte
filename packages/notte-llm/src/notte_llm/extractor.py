import datetime as dt
import json

from notte_core.common.logging import logger
from notte_core.common.types import TResponseFormat
from notte_core.data.pruning import MarkdownPruningPipe
from notte_core.data.space import DictBaseModel, NoStructuredData, StructuredData
from pydantic import BaseModel

from notte_llm.service import LLMService


class _Hotel(BaseModel):
    city: str
    price: int
    currency: str
    availability: str
    return_date: str
    link: str


class _Hotels(BaseModel):
    hotels: list[_Hotel]


class LlmExtractor:
    """
    Structured extractor (`notte_core.data.extraction.StructuredExtractor`) that asks an LLM to turn the
    markdown of a page into JSON, optionally validated against a Pydantic model.

    The model defaults to `NOTTE_LLM_MODEL` (see `notte_llm.config.LlmSettings`); a model passed to
    `extract` is used for that call only.
    """

    def __init__(self, model: str | None = None, llmserve: LLMService | None = None) -> None:
        self.llmserve: LLMService = llmserve or LLMService(base_model=model)
        self._per_call_services: dict[str, LLMService] = {}

    def _service(self, model: str | None) -> LLMService:
        if model is None or model == self.llmserve.base_model:
            return self.llmserve
        if model not in self._per_call_services:
            self._per_call_services[model] = LLMService(base_model=model)
        return self._per_call_services[model]

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

    async def extract(
        self,
        *,
        url: str,
        document: str,
        response_format: type[TResponseFormat] | None,
        instructions: str | None,
        model: str | None = None,
        use_link_placeholders: bool = True,
    ) -> StructuredData[BaseModel]:
        llmserve = self._service(model)
        verbose = llmserve.verbose
        masked_document = MarkdownPruningPipe.mask(document)
        document = llmserve.clip_tokens(masked_document.content if use_link_placeholders else document)
        match (response_format, instructions):
            case (None, None):
                raise ValueError("response_format and instructions cannot be both None")
            case (None, _):
                structured = await llmserve.structured_completion(
                    prompt_id="extract-without-json-schema",
                    variables={
                        "document": document,
                        "instructions": instructions,
                        "success_example": self.success_example().model_dump_json(),
                        "failure_example": self.failure_example().model_dump_json(),
                        "timestamp": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                    },
                    response_format=StructuredData[DictBaseModel],
                    use_strict_response_format=False,
                )
                if verbose:
                    logger.trace(f"LLM Structured Response with no schema:\n{structured}")
                # Unmask placeholders if requested
                if use_link_placeholders and structured.data is not None:
                    structured.data = MarkdownPruningPipe.unmask_pydantic(
                        document=masked_document, data=structured.data
                    )
                return structured
            case (_response_format, _):
                response: StructuredData[DictBaseModel] = await llmserve.structured_completion(
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
                        "timestamp": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                        "instructions": instructions,
                    },
                )
                if verbose:
                    logger.trace(f"LLM Structured Response with user provided schema:\n{response}")
                # try model_validate
                if not response.success or response.data is None:
                    return response
                try:
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
                        error=f"Cannot validate response into the provided schema for data={data.model_dump_json()}. Error: {e}",
                        data=None,
                    )
