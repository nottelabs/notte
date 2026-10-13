"""Live helpers must reject credential destinations before constructing a client."""

import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(params=["captcha_polling_live.py", "hcaptcha_polling_live.py"])
def validate(request):
    return runpy.run_path(str(ROOT / "scripts" / request.param))["validate_api_url"]


@pytest.mark.parametrize("url", ["https://preview-7-dev-test.notte.cc", "https://us-staging.notte.cc/"])
def test_allows_approved_test_origins(validate, url):
    assert validate(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "http://preview-7-dev-test.notte.cc",
        "https://api.notte.cc",
        "https://evil.example",
        "https://preview-7-dev-test.notte.cc.evil.example",
        "https://preview-7-dev-test.notte.cc@evil.example",
        "https://user:password@preview-7-dev-test.notte.cc",  # pragma: allowlist secret - rejected test URL
        "https://preview-7-dev-test.notte.cc:444",
        "https://preview-7-dev-test.notte.cc/path",
        "https://preview-7-dev-test.notte.cc?redirect=evil",
        "https://preview-7-dev-test.notte.cc#fragment",
    ],
)
def test_rejects_other_destinations(validate, url):
    with pytest.raises(ValueError):
        validate(url)
