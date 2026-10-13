import io
from base64 import b64decode

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from notte_core.utils.image import get_images_as_base64
from PIL import Image


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_get_images_as_base64_downloads_over_aiohttp() -> None:
    png = _png_bytes()

    async def logo(_: web.Request) -> web.Response:
        return web.Response(body=png, content_type="image/png")

    app = web.Application()
    app.router.add_get("/logo.png", logo)

    # A local server keeps the test independent of any external website.
    async with TestServer(app) as server:
        image_url = str(server.make_url("/logo.png"))
        missing_url = str(server.make_url("/missing.png"))
        result = await get_images_as_base64([image_url, missing_url])

    # The missing image is skipped; the real one is downloaded and encoded.
    assert result["total_images"] == 1
    [image] = result["images"]
    assert image["url"] == image_url
    assert image["content_type"].startswith("image/png")
    assert image["size"] == len(png)
    assert b64decode(image["data"]) == png
