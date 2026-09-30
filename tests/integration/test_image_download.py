from base64 import b64decode

import pytest
from notte_core.utils.image import get_images_as_base64

IMAGE_URL = "https://www.python.org/static/img/python-logo.png"
MISSING_URL = "https://www.python.org/static/img/does-not-exist.png"


@pytest.mark.asyncio
async def test_get_images_as_base64_downloads_over_aiohttp() -> None:
    result = await get_images_as_base64([IMAGE_URL, MISSING_URL])

    # The missing image is skipped; the real one is downloaded and encoded.
    assert result["total_images"] == 1
    [image] = result["images"]
    assert image["url"] == IMAGE_URL
    assert image["content_type"].startswith("image/png")
    data = b64decode(image["data"])
    assert len(data) == image["size"] > 0
    assert data.startswith(b"\x89PNG")
