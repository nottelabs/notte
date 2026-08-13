import pytest
from notte_core.data.space import DataSpace, DictBaseModel, StructuredData
from notte_core.errors.processing import ScrapeFailedError
from pydantic import BaseModel, RootModel, ValidationError


class Verification(BaseModel):
    status: str
    code: str


PAYLOAD = {"status": "found", "code": "463092"}


def test_get_validates_raw_payload_into_the_parametrized_schema():
    """A raw JSON payload is wrapped in a RootModel, get() validates it back into the schema."""
    structured = StructuredData[Verification].model_validate({"success": True, "data": PAYLOAD})
    assert isinstance(structured.data, RootModel)
    assert structured.get() == Verification(status="found", code="463092")


def test_get_raises_when_the_payload_does_not_match_the_schema():
    structured = StructuredData[Verification].model_validate({"success": True, "data": {"unrelated": 1}})
    with pytest.raises(ValidationError):
        _ = structured.get()


def test_get_returns_the_root_model_when_no_schema_is_known():
    """`StructuredData[BaseModel]` (what `DataSpace.structured` is) carries no schema to validate against."""
    space = DataSpace.model_validate({"markdown": "content", "structured": {"success": True, "data": PAYLOAD}})
    assert space.structured is not None
    data = space.structured.get()
    assert isinstance(data, BaseModel)
    assert data.model_dump() == PAYLOAD


def test_get_returns_the_root_model_for_dict_base_model():
    structured = StructuredData[DictBaseModel](success=True, data=DictBaseModel(PAYLOAD))
    assert structured.get().model_dump() == PAYLOAD


def test_get_returns_model_payloads_untouched():
    verification = Verification(status="found", code="463092")
    assert DataSpace.from_structured(verification).structured.get() is verification  # pyright: ignore[reportOptionalMemberAccess]


def test_get_raises_on_failed_extraction():
    structured = StructuredData[Verification](success=False, error="nothing to extract", data=None)
    with pytest.raises(ScrapeFailedError):
        _ = structured.get()
