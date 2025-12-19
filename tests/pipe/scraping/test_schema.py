"""Tests for schema scraping pipe."""

from typing import Any

import pytest
from notte_browser.scraping.pruning import MarkdownPruningPipe
from notte_browser.scraping.schema import SchemaScrapingPipe
from notte_core.data.space import DictBaseModel, StructuredData
from notte_llm.service import LLMService
from typing_extensions import override


class MockLLMServiceForSchema(LLMService):
    """Mock LLM service that returns structured data with placeholders."""

    def __init__(self, mock_data: dict[str, Any]) -> None:
        """Initialize with mock data that contains placeholders."""
        self.mock_data = mock_data
        self.tokenizer = None  # type: ignore[assignment]
        self.base_model = "mock-model"

    @override
    def clip_tokens(self, document: str, max_tokens: int | None = None) -> str:
        """Return document as-is for testing."""
        return document

    @override
    async def structured_completion(
        self,
        prompt_id: str,
        response_format: type[Any],
        variables: dict[str, Any] | None = None,
        use_strict_response_format: bool = True,
    ) -> StructuredData[DictBaseModel]:
        """Return mock structured data with placeholders."""
        return StructuredData[DictBaseModel](
            success=True,
            error=None,
            data=DictBaseModel(self.mock_data),
        )


@pytest.mark.asyncio
async def test_unmask_placeholders_with_instructions_only() -> None:
    """Test that placeholders are unmasked when using instructions without response_format."""
    # Create markdown with URLs
    markdown = """
    # Hotels

    ## Hotel 1
    Name: Grand Hotel Bellevue London
    Review Score: 8.2
    Reviewers: 196
    Room Type: Small Double Room
    Booking: [Book here](https://booking.com/hotel1)

    ## Hotel 2
    Name: The Franklin London
    Review Score: 8.4
    Reviewers: 454
    Room Type: Superior Double Room
    Booking: [Book here](https://booking.com/hotel2)
    """

    # Mask the markdown to get placeholders
    masked_doc = MarkdownPruningPipe.mask(markdown)

    # Verify masking worked
    assert "link1" in masked_doc.content or "link2" in masked_doc.content
    assert "https://booking.com/hotel1" in masked_doc.links.values()
    assert "https://booking.com/hotel2" in masked_doc.links.values()

    # Create mock LLM service that returns data with placeholders
    # The LLM would return placeholders like "link1", "link2" in the structured data
    mock_data_with_placeholders = {
        "hotels": [
            {
                "name": "Grand Hotel Bellevue London",
                "review_score": "8.2",
                "reviewers": "196",
                "room_type": "Small Double Room",
                "booking_url": "link1",  # This is a placeholder that should be unmasked
            },
            {
                "name": "The Franklin London",
                "review_score": "8.4",
                "reviewers": "454",
                "room_type": "Superior Double Room",
                "booking_url": "link2",  # This is a placeholder that should be unmasked
            },
        ]
    }

    llm_service = MockLLMServiceForSchema(mock_data_with_placeholders)
    schema_pipe = SchemaScrapingPipe(llmserve=llm_service)

    # Call forward with instructions (no response_format) and use_link_placeholders=True
    result = await schema_pipe.forward(
        url="https://example.com",
        document=markdown,
        response_format=None,
        instructions="Extract booking results (name, review_score, reviewers, room_type, booking_url)",
        verbose=False,
        use_link_placeholders=True,
    )

    # Verify the result is successful
    assert result.success is True
    assert result.data is not None

    # Get the actual data
    data = result.get()
    assert isinstance(data, dict)
    assert "hotels" in data
    assert len(data["hotels"]) == 2

    # CRITICAL: Verify that placeholders were unmasked to actual URLs
    hotel1 = data["hotels"][0]
    assert hotel1["booking_url"] == "https://booking.com/hotel1", (
        f"Expected unmasked URL 'https://booking.com/hotel1', got '{hotel1['booking_url']}'"
    )

    hotel2 = data["hotels"][1]
    assert hotel2["booking_url"] == "https://booking.com/hotel2", (
        f"Expected unmasked URL 'https://booking.com/hotel2', got '{hotel2['booking_url']}'"
    )
