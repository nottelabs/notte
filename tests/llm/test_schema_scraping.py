"""Tests for schema scraping pipe."""

import os
from typing import Any

import pytest
from dotenv import load_dotenv
from notte_core.errors import LLMParsingError
from notte_core.pruning import mask_markdown
from notte_llm.extractor import LlmExtractor
from notte_llm.service import LLMService
from pydantic import BaseModel, RootModel, ValidationError
from typing_extensions import override

_ = load_dotenv()


class MockLLMServiceForSchema(LLMService):
    """Mock LLM service that returns structured data with placeholders."""

    def __init__(self, mock_data: Any) -> None:
        """Initialize with mock data that contains placeholders."""
        self.mock_data = mock_data
        self.base_model = "mock-model"
        self.verbose = False

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
        extra_body: dict[str, Any] | None = None,
    ) -> Any:
        """Honor the service contract: return an instance of the requested wire model."""
        try:
            return response_format.model_validate({"success": True, "error": None, "data": self.mock_data})
        except ValidationError as e:
            raise LLMParsingError("Response does not match the requested extraction schema") from e


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
    schema_pipe = LlmExtractor(llmserve=MockLLMServiceForSchema(mock_data))

    async def extract():
        return await schema_pipe.extract(
            url="https://example.com",
            document="[A](https://example.com/a) [B](https://example.com/b)",
            response_format=response_format,
            instructions="Extract test data",
            use_link_placeholders=True,
        )

    if expected_success:
        result = await extract()
        assert result.success
        assert isinstance(result.data, response_format)
    else:
        with pytest.raises(LLMParsingError):
            await extract()


@pytest.mark.asyncio
async def test_schema_scraping_unmasks_root_model_list() -> None:
    schema_pipe = LlmExtractor(
        llmserve=MockLLMServiceForSchema(
            [
                {"rank": 1, "title": "A", "url": "link1"},
                {"rank": 2, "title": "B", "url": "link2"},
            ]
        )
    )

    result = await schema_pipe.extract(
        url="https://example.com",
        document="[A](https://example.com/a) [B](https://example.com/b)",
        response_format=RootItemList,
        instructions="Extract items",
        use_link_placeholders=True,
    )

    assert result.success is True
    assert isinstance(result.data, RootItemList)
    assert [item.url for item in result.data.root] == ["https://example.com/a", "https://example.com/b"]


@pytest.mark.live
@pytest.mark.skipif(not (os.getenv("NOTTE_LLM_API_KEY") or os.getenv("OPENROUTER_API_KEY")), reason="requires LLM key")
@pytest.mark.asyncio
async def test_schema_scraping_root_model_list_with_real_llm_round_trip() -> None:
    schema_pipe = LlmExtractor(llmserve=LLMService())

    result = await schema_pipe.extract(
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
    masked_doc = mask_markdown(markdown)

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
    schema_pipe = LlmExtractor(llmserve=llm_service)

    # Call extract with instructions (no response_format) and use_link_placeholders=True
    result = await schema_pipe.extract(
        url="https://example.com",
        document=markdown,
        response_format=None,
        instructions="Extract booking results (name, review_score, reviewers, room_type, booking_url)",
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "schema,payload",
    [
        (RootItemList, [{"rank": 1, "title": "A", "url": "link1"}]),
        (WrappedItemList, {"items": [{"rank": 1, "title": "A", "url": "link1"}]}),
        (RootStringList, ["alpha", "beta"]),
        (RootString, "alpha"),
        (RootDict, {"a": 1, "b": 2}),
    ],
)
async def test_extractor_round_trip_with_compatible_http_client(schema, payload, monkeypatch):
    import json

    import httpx
    from notte_llm.engine import LLMEngine

    monkeypatch.setenv("NOTTE_LLM_API_KEY", "test-key")
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        assert body["response_format"]["type"] == ("json_object" if schema == RootDict else "json_schema")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps({"success": True, "error": None, "data": payload})}}]},
        )

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr("notte_llm.service.LLMEngine", lambda **kwargs: LLMEngine(transport=transport, **kwargs))
    result = await LlmExtractor().extract(
        url="https://example.com",
        document="[A](https://example.com/a)",
        response_format=schema,
        instructions="Extract the entries",
    )
    assert result.success
    assert isinstance(result.data, schema)
    if schema == RootItemList:
        assert result.data.root[0].url == "https://example.com/a"
    elif schema == WrappedItemList:
        assert result.data.items[0].url == "https://example.com/a"
    else:
        assert result.data.root == payload
    if schema != RootDict:
        wire_schema = bodies[0]["response_format"]["json_schema"]["schema"]
        assert "RootModel[Any]" not in json.dumps(wire_schema)


@pytest.mark.asyncio
async def test_extractor_preserves_failure_wrapper_and_retries_bad_data(monkeypatch):
    import json

    import httpx
    from notte_llm.engine import LLMEngine

    monkeypatch.setenv("NOTTE_LLM_API_KEY", "test-key")
    replies = iter(
        [
            {"success": True, "data": {"items": "wrong"}},
            {"success": False, "error": "No items on this page", "data": None},
        ]
    )
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(next(replies))}}]})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr("notte_llm.service.LLMEngine", lambda **kwargs: LLMEngine(transport=transport, **kwargs))
    result = await LlmExtractor().extract(
        url="https://example.com", document="# Empty", response_format=WrappedItemList, instructions=None
    )
    assert not result.success
    assert result.error == "No items on this page"
    assert result.data is None
    assert len(bodies) == 2
    assert "Error parsing LLM response" in bodies[-1]["messages"][-1]["content"]


def test_extraction_wire_wrapper_requires_data_and_preserves_errors():
    from notte_llm.extractor import _ExtractionResult
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="data field is None"):
        _ExtractionResult[PlainItem].model_validate({"success": True, "data": None})
    result = _ExtractionResult[PlainItem].model_validate({"success": True, "error": "Nothing found", "data": None})
    assert not result.success


@pytest.mark.asyncio
@pytest.mark.parametrize("use_link_placeholders", [True, False])
async def test_extractor_preserves_aliased_fields(use_link_placeholders, monkeypatch):
    import json

    import httpx
    from notte_llm.engine import LLMEngine
    from pydantic import Field

    class AliasedItem(BaseModel):
        title: str = Field(alias="pageTitle")
        link: str = Field(alias="pageLink")

    monkeypatch.setenv("NOTTE_LLM_API_KEY", "test-key")

    def handler(_):
        data = {"pageTitle": "A", "pageLink": "link1" if use_link_placeholders else "https://example.com/a"}
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps({"success": True, "data": data})}}]}
        )

    monkeypatch.setattr(
        "notte_llm.service.LLMEngine", lambda **kwargs: LLMEngine(transport=httpx.MockTransport(handler), **kwargs)
    )
    result = await LlmExtractor().extract(
        url="https://example.com",
        document="[A](https://example.com/a)",
        response_format=AliasedItem,
        instructions=None,
        use_link_placeholders=use_link_placeholders,
    )
    assert result.success
    assert isinstance(result.data, AliasedItem)
    assert result.data.title == "A"
    assert result.data.link == "https://example.com/a"


@pytest.mark.asyncio
@pytest.mark.parametrize("recursive", [True, False])
async def test_extractor_keeps_recursive_and_dictionary_contracts(recursive, monkeypatch):
    import json

    import httpx
    from notte_llm.engine import LLMEngine
    from pydantic import Field

    class Node(BaseModel):
        name: str
        children: list["Node"] = Field(default_factory=list)

    class Metadata(BaseModel):
        metadata: dict[str, str]

    schema = Node if recursive else Metadata
    data = (
        {"name": "root", "children": [{"name": "child", "children": []}]}
        if recursive
        else {"metadata": {"source": "example", "type": "page"}}
    )
    monkeypatch.setenv("NOTTE_LLM_API_KEY", "test-key")

    def handler(request):
        body = json.loads(request.content)
        assert body["response_format"] == {"type": "json_object"}
        raw = json.loads(body["messages"][-1]["content"].split("JSON schema: ", 1)[1])
        if not recursive:
            assert raw["$defs"]["Metadata"]["properties"]["metadata"]["additionalProperties"] == {"type": "string"}
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps({"success": True, "data": data})}}]}
        )

    monkeypatch.setattr(
        "notte_llm.service.LLMEngine", lambda **kwargs: LLMEngine(transport=httpx.MockTransport(handler), **kwargs)
    )
    result = await LlmExtractor().extract(
        url="https://example.com", document="# Example", response_format=schema, instructions=None
    )
    assert result.success
    assert result.data.model_dump() == data
