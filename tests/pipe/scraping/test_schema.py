"""Tests for schema scraping pipe."""

import os
from typing import Any

import pytest
from dotenv import load_dotenv
from notte_browser.scraping.pruning import MarkdownPruningPipe
from notte_browser.scraping.schema import SchemaScrapingPipe
from notte_core.common.config import LlmModel
from notte_core.data.space import DictBaseModel, StructuredData
from notte_llm.service import LLMService
from pydantic import BaseModel, RootModel
from typing_extensions import override

_ = load_dotenv()


class MockLLMServiceForSchema(LLMService):
    """Mock LLM service that returns structured data with placeholders."""

    def __init__(self, mock_data: Any) -> None:
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


class ScrapedItem(BaseModel):
    rank: int | None = None
    title: str | None = None
    url: str | None = None


class RootItemList(RootModel[list[ScrapedItem]]):
    root: list[ScrapedItem]


class RootStringList(RootModel[list[str]]):
    root: list[str]


class RootString(RootModel[str]):
    root: str


class RootDict(RootModel[dict[str, int]]):
    root: dict[str, int]


class WrappedItemList(BaseModel):
    items: list[ScrapedItem]


class PlainItem(BaseModel):
    rank: int | None = None
    title: str | None = None


class LinkList(RootModel[list[str]]):
    root: list[str]


class WeirdWrappedRoots(BaseModel):
    primary: ScrapedItem
    links: LinkList


@pytest.mark.parametrize(
    ("response_format", "mock_data", "expected_success"),
    [
        (RootItemList, [{"rank": 1, "title": "A"}, {"rank": 2, "title": "B"}], True),
        (RootItemList, {"items": [{"rank": 1, "title": "A"}]}, False),
        (RootStringList, ["alpha", "beta"], True),
        (RootString, "alpha", True),
        (RootDict, {"a": 1, "b": 2}, True),
        (RootDict, [{"a": 1}], False),
        (WrappedItemList, {"items": [{"rank": 1, "title": "A"}]}, True),
        (WrappedItemList, [{"rank": 1, "title": "A"}], False),
        (PlainItem, {"rank": 1, "title": "A"}, True),
        (PlainItem, [{"rank": 1, "title": "A"}], False),
        (
            WeirdWrappedRoots,
            {"primary": {"rank": 1, "title": "A", "url": "link1"}, "links": ["link1", "link2"]},
            True,
        ),
    ],
)
@pytest.mark.asyncio
async def test_schema_scraping_validates_root_model_and_base_model_shapes(
    response_format: type[BaseModel], mock_data: Any, expected_success: bool
) -> None:
    schema_pipe = SchemaScrapingPipe(llmserve=MockLLMServiceForSchema(mock_data))

    result = await schema_pipe.forward(
        url="https://example.com",
        document="[A](https://example.com/a) [B](https://example.com/b)",
        response_format=response_format,
        instructions="Extract test data",
        verbose=False,
        use_link_placeholders=True,
    )

    assert result.success is expected_success
    if expected_success:
        assert result.data is not None
        assert isinstance(result.data, response_format)
    else:
        assert result.data is None
        assert result.error is not None
        assert "Cannot validate response into the provided schema" in result.error


@pytest.mark.asyncio
async def test_schema_scraping_unmasks_root_model_list() -> None:
    schema_pipe = SchemaScrapingPipe(
        llmserve=MockLLMServiceForSchema(
            [
                {"rank": 1, "title": "A", "url": "link1"},
                {"rank": 2, "title": "B", "url": "link2"},
            ]
        )
    )

    result = await schema_pipe.forward(
        url="https://example.com",
        document="[A](https://example.com/a) [B](https://example.com/b)",
        response_format=RootItemList,
        instructions="Extract items",
        verbose=False,
        use_link_placeholders=True,
    )

    assert result.success is True
    assert isinstance(result.data, RootItemList)
    assert [item.url for item in result.data.root] == ["https://example.com/a", "https://example.com/b"]


@pytest.mark.skipif("OPENAI_API_KEY" not in os.environ, reason="requires OPENAI_API_KEY")
@pytest.mark.asyncio
async def test_schema_scraping_root_model_list_with_real_llm_round_trip() -> None:
    schema_pipe = SchemaScrapingPipe(llmserve=LLMService(base_model=LlmModel.openai))

    result = await schema_pipe.forward(
        url="https://example.com/products",
        document="""
        # Product ranking

        1. Atlas Notebook - https://example.com/atlas
        2. Beacon Pen - https://example.com/beacon
        """,
        response_format=RootItemList,
        instructions=(
            "Extract the two product ranking entries. Return only the ranked items from the document with rank, "
            "title, and url populated."
        ),
        verbose=False,
        use_link_placeholders=False,
    )

    assert result.success is True, result.error
    assert isinstance(result.data, RootItemList)
    assert result.data.root == [
        ScrapedItem(rank=1, title="Atlas Notebook", url="https://example.com/atlas"),
        ScrapedItem(rank=2, title="Beacon Pen", url="https://example.com/beacon"),
    ]


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
