# @sniptest filename=uptime_monitor.py
from datetime import datetime

from notte_sdk import NotteClient


def run(target_url: str, expected_text: str):
    """Monitor site uptime."""
    client = NotteClient()

    try:
        with client.Session(idle_timeout_minutes=2) as session:
            session.execute(type="goto", url=target_url)
            content = session.scrape()

            is_up = expected_text in content

        return {"status": "up" if is_up else "down", "url": target_url, "checked_at": datetime.now().isoformat()}

    except Exception as e:
        return {"status": "error", "url": target_url, "error": str(e), "checked_at": datetime.now().isoformat()}
