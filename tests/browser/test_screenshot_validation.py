from base64 import b64encode
from io import BytesIO
from types import SimpleNamespace

import pytest
from notte_core.ast import SecureScriptRunner
from notte_core.browser.observation import Screenshot
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
    assert screenshot.bytes(type="raw") == raw
    assert screenshot.model_dump()["raw"] == b64encode(raw).decode("ascii")


def test_observation_does_not_expose_builtins_to_restricted_scripts() -> None:
    """Importing the bytes type must not expose the builtins module to scripts."""
    script = """
def run():
    import notte_core.browser.observation as observation
    return observation.builtins
"""

    runner = SecureScriptRunner(SimpleNamespace())

    assert runner.run_script(script, restricted=True) is None
