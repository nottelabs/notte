import base64
import json

import httpx

CODE = "orbit-fixture"


def response(action: dict | None, *, safety: bool = False, index: int = 0) -> dict:
    item = (
        {
            "id": f"call_fixture_{index}",
            "type": "computer_call",
            "call_id": f"call_fixture_{index}",
            "status": "completed",
            "pending_safety_checks": [{"id": "review_fixture", "code": "fixture", "message": "Review needed"}]
            if safety
            else [],
            "action": action,
        }
        if action
        else {
            "id": "msg_fixture",
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": "Complete", "annotations": []}],
        }
    )
    return {
        "id": "resp_fixture",
        "object": "response",
        "status": "completed",
        "model": "tzafon.northstar-cua-fast-1.6",
        "output": [item],
    }


class Wire:
    def __init__(self, mode: str = "protocol", real_screenshot: bool = False):
        self.mode = mode
        self.real_screenshot = real_screenshot
        self.requests: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.method == "POST" and request.url.path == "/v1/responses"
        assert request.headers["authorization"] == "Bearer fixture-provider-key"
        body = json.loads(request.content)
        assert body["store"] is False and "previous_response_id" not in body
        assert body["model"] == "tzafon.northstar-cua-fast-1.6"
        assert body["tools"] == [
            {"type": "computer_use", "environment": "browser", "display_width": 1024, "display_height": 768}
        ]
        if self.real_screenshot:
            item = body["input"][-1]
            image = (
                item["output"]["image_url"]
                if item.get("type") == "computer_call_output"
                else item["content"][1]["image_url"]
            )
            png = base64.b64decode(image.split(",")[1])
            assert png.startswith(b"\x89PNG\r\n\x1a\n") and len(png) > 1000
            assert int.from_bytes(png[16:20], "big") == 1024 and int.from_bytes(png[20:24], "big") == 768
        self.requests.append(body)
        if self.mode == "reject":
            return httpx.Response(401, json={"error": {"message": "PRIVATE_FIXTURE_BODY"}})
        if self.mode == "limit":
            action = {"type": "screenshot"}
        elif self.mode in ["safety", "out-of-bounds"]:
            action = {"type": "click", "x": 1000 if self.mode == "out-of-bounds" else 160, "y": 260, "button": "left"}
        elif len(self.requests) == 1:
            action = {"type": "point_and_type", "x": 160, "y": 260, "text": CODE}
        elif len(self.requests) == 2:
            action = {"type": "keypress", "keys": ["ENTER"]}
        else:
            action = None
        return httpx.Response(200, json=response(action, safety=self.mode == "safety", index=len(self.requests)))
