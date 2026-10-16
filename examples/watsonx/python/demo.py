import asyncio
import base64
import json
import os

import requests
from notte_sdk import NotteClient


class WatsonxExampleError(RuntimeError):
    pass


def safe_failure(error: Exception, stage: str, session_id: str) -> WatsonxExampleError:
    if isinstance(error, WatsonxExampleError):
        return error
    status = getattr(getattr(error, "response", None), "status_code", None)
    detail = f" HTTP {status}" if isinstance(status, int) and 100 <= status <= 599 else ""
    return WatsonxExampleError(
        f"Screenshot analysis failed: {stage} [{type(error).__name__}]{detail} (session {session_id})"
    )


def describe(image: bytes, http: requests.Session) -> str:
    token = http.post(
        "https://iam.cloud.ibm.com/identity/token",
        data={"grant_type": "urn:ibm:params:oauth:grant-type:apikey", "apikey": os.environ["WATSONX_API_KEY"]},
        timeout=30,
        allow_redirects=False,
    )
    if not 200 <= token.status_code < 300:
        raise requests.HTTPError(response=token)
    access_token = token.json().get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise RuntimeError("IBM IAM did not return an access token")
    response = http.post(
        f"{os.getenv('WATSONX_URL', 'https://us-south.ml.cloud.ibm.com').rstrip('/')}/ml/v1/text/chat",
        params={"version": "2024-05-31"},
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "project_id": os.environ["WATSONX_PROJECT_ID"],
            "model_id": os.environ["WATSONX_MODEL_ID"],
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe the visible page heading in one sentence."},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64," + base64.b64encode(image).decode()},
                        },
                    ],
                }
            ],
            "max_tokens": 200,
        },
        timeout=30,
        allow_redirects=False,
    )
    if not 200 <= response.status_code < 300:
        raise requests.HTTPError(response=response)
    description = response.json()["choices"][0]["message"]["content"]
    if not isinstance(description, str) or not description.strip():
        raise RuntimeError("The vision model did not return text")
    return description


async def run_demo(http: requests.Session | None = None) -> dict:
    for name in ["WATSONX_API_KEY", "WATSONX_PROJECT_ID", "WATSONX_MODEL_ID"]:
        if not os.environ.get(name):
            raise RuntimeError(f"Set {name}")
    client = NotteClient()
    session_id = "not-created"
    stage = "create browser"
    try:
        async with client.Session(max_duration_minutes=3) as session:
            session_id = session.session_id
            try:
                stage = "capture page"
                page = await session.apage
                await page.goto("https://example.com", wait_until="domcontentloaded")
                await page.locator("body").wait_for()
                image = await page.screenshot(type="png")
                stage = "describe screenshot"
                with http or requests.Session() as transport:
                    description = await asyncio.to_thread(describe, image, transport)
            except Exception as error:
                raise safe_failure(error, stage, session_id) from None
        return {"description": description, "session_id": session_id}
    except Exception as error:
        raise safe_failure(error, stage, session_id) from None


if __name__ == "__main__":
    try:
        with asyncio.Runner() as runner:
            print(json.dumps(runner.run(run_demo())))
    except Exception as error:
        print(str(error))
        raise SystemExit(1) from None
