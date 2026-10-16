# @sniptest filename=notte_agent_browser.py
# @sniptest typecheck_only=true
import json
import os
import subprocess
from typing import Any

from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    command = ["agent-browser", "--session", f"notte-{session.session_id}", "--json"]
    environment = {**os.environ, "AGENT_BROWSER_CDP": session.cdp_url()}

    def browser(*args: str) -> dict[str, Any]:
        try:
            completed = subprocess.run(
                command + list(args), env=environment, capture_output=True, text=True, timeout=120, check=False
            )
            response = json.loads(completed.stdout)
            if (
                completed.returncode
                or not isinstance(response, dict)
                or response.get("success") is not True
                or not isinstance(response.get("data"), dict)
            ):
                raise RuntimeError("agent-browser command failed")
            return response["data"]
        except (OSError, subprocess.SubprocessError, ValueError, TypeError, KeyError):
            raise RuntimeError("agent-browser command failed") from None

    failed = False
    try:
        _ = browser("open", "https://example.com")
        title = browser("get", "title")["title"]
        if not isinstance(title, str):
            raise RuntimeError("The title was not returned")
        print(title)
        result = {"title": title, "session_id": session.session_id}
    except BaseException:
        failed = True
        raise
    finally:
        try:
            _ = browser("close")
        except Exception:
            if not failed:
                raise
