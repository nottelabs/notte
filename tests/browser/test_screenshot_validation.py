from base64 import b64encode
from io import BytesIO
from typing import get_type_hints

import pytest
from notte_core.observation import Screenshot
from PIL import Image


@pytest.mark.parametrize("encoded", [False, True], ids=["bytes", "base64"])
def test_screenshot_accepts_image_bytes(encoded: bool) -> None:
    """The bytes() method must not shadow the raw field's type on Python 3.14."""
    buffer = BytesIO()
    Image.new("RGB", (2, 2), color="white").save(buffer, format="JPEG")
    raw = buffer.getvalue()
    data = {"raw": b64encode(raw).decode("ascii") if encoded else raw}

    screenshot = Screenshot.model_validate(data)

    assert Screenshot.model_fields["raw"].annotation is bytes
    assert screenshot.raw == raw
    assert screenshot.bytes() == raw
    assert screenshot.model_dump()["raw"] == b64encode(raw).decode("ascii")


def test_observation_does_not_expose_builtins_module() -> None:
    """V2 removed restricted execution; keep its module namespace free of builtins."""
    import notte_core.observation as observation

    assert not hasattr(observation, "builtins")


def test_screenshot_annotations_stay_bytes_after_model_rebuild() -> None:
    Screenshot.model_rebuild(force=True)

    assert Screenshot.model_fields["raw"].annotation is bytes
    assert get_type_hints(Screenshot.validate_raw)["return"] is bytes
    assert get_type_hints(Screenshot.bytes)["return"] is bytes


def test_screenshot_does_not_expose_raw_data_in_validation_errors() -> None:
    with pytest.raises(ValueError) as error:
        Screenshot(raw="PRIVATE-CONTENT!")

    assert "PRIVATE-CONTENT" not in str(error.value)


def test_screenshot_json_roundtrip() -> None:
    buffer = BytesIO()
    Image.new("RGB", (2, 2)).save(buffer, format="JPEG")
    screenshot = Screenshot(raw=buffer.getvalue())

    restored = Screenshot.model_validate_json(screenshot.model_dump_json())

    assert restored.raw == screenshot.raw
    assert restored.bytes() == screenshot.raw
