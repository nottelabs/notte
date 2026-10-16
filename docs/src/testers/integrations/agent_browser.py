# @sniptest filename=notte_agent_browser.py
# @sniptest typecheck_only=true
import json
import subprocess
from typing import Any

from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    command = ["agent-browser", "--session", f"notte-{session.session_id}", "--json"]

    def browser(*args: str) -> dict[str, Any]:
        try:
            completed = subprocess.run(command + list(args), capture_output=True, text=True, timeout=120, check=False)
        except (OSError, subprocess.SubprocessError):
            raise RuntimeError("agent-browser command failed") from None
        if completed.returncode:
            # CLI errors can include the authenticated CDP URL.
            raise RuntimeError("agent-browser command failed")
        response = json.loads(completed.stdout)
        if not response["success"]:
            raise RuntimeError("agent-browser reported an unsuccessful command")
        return response["data"]

    try:
        _ = browser("connect", session.cdp_url())
        _ = browser("open", "https://example.com")
        title = browser("get", "title")["title"]
        print(title)
        result = {"title": title, "session_id": session.session_id}
    finally:
        _ = browser("close")
