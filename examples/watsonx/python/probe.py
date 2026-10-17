import asyncio
import base64
import json
import sys

from demo import run_demo
from test_demo import Transport


class ScreenshotTransport(Transport):
    def post(self, url, **kwargs):
        if len(self.calls) == 1:
            image = kwargs["json"]["messages"][0]["content"][1]["image_url"]["url"]
            png = base64.b64decode(image.split(",")[1])
            assert png.startswith(b"\x89PNG\r\n\x1a\n") and len(png) > 1000
        return super().post(url, **kwargs)


try:
    with asyncio.Runner() as runner:
        print(json.dumps(runner.run(run_demo(ScreenshotTransport(sys.argv[1])))))
except Exception as error:
    print(str(error))
    raise SystemExit(1) from None
