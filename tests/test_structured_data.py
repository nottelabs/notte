import pytest
from notte_core.data.space import DataSpace, StructuredData
from notte_core.errors.processing import ScrapeFailedError
from pydantic import BaseModel, RootModel


class Verification(BaseModel):
    status: str
    code: str | None = None


def test_get_returns_plain_dict_for_dict_payload():
    """A dict payload is wrapped in a RootModel, so `get()` returns the unwrapped dict."""
    structured = StructuredData(success=True, data={"status": "found", "code": "463092"})

    assert isinstance(structured.data, RootModel)
    data = structured.get()
    assert isinstance(data, dict)
    assert not isinstance(data, BaseModel)
    assert data == {"status": "found", "code": "463092"}


def test_get_returns_model_for_model_payload():
    """A model payload is returned as-is, so `get()` returns a `BaseModel`."""
    structured = StructuredData[Verification](success=True, data=Verification(status="found", code="463092"))

    data = structured.get()
    assert isinstance(data, Verification)
    assert data.model_dump() == {"status": "found", "code": "463092"}


def test_get_returns_plain_dict_for_deserialized_response():
    """Structured data deserialized from a JSON response also yields a plain dict."""
    space = DataSpace.model_validate(
        {
            "markdown": "# page",
            "structured": {"success": True, "error": None, "data": {"status": "found", "code": "463092"}},
        }
    )

    assert space.structured is not None
    data = space.structured.get()
    assert isinstance(data, dict)
    assert data == {"status": "found", "code": "463092"}


def test_get_raises_on_failed_extraction():
    structured = StructuredData[Verification](success=False, error="boom", data=None)

    with pytest.raises(ScrapeFailedError):
        _ = structured.get()
