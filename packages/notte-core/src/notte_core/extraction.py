from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from notte_core.data import StructuredData


@runtime_checkable
class StructuredExtractor(Protocol):
    """Turns a scraped page into structured data.

    Sessions only scrape markdown themselves; `scrape(instructions=..., response_format=...)` hands the
    markdown to an extractor. The `notte-llm` package provides the default LLM-based implementation
    (`notte_llm.LlmExtractor`), and any object with this method can be passed instead.
    """

    async def extract(
        self,
        *,
        url: str,
        document: str,
        response_format: type[BaseModel] | None,
        instructions: str | None,
        model: str | None = None,
        use_link_placeholders: bool = True,
    ) -> StructuredData[BaseModel]:
        """Extract data from `document` (the markdown of the page at `url`).

        Args:
            url: URL of the scraped page.
            document: Markdown of the page.
            response_format: Pydantic model the data must follow, if any.
            instructions: What to extract, if any. At least one of `response_format` and `instructions` is set.
            model: Model to use for this call, if the extractor supports choosing one.
            use_link_placeholders: Replace link and image URLs by short placeholders while extracting.
        """
        ...
