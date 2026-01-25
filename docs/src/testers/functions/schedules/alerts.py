# @sniptest filename=alerts.py
import os

import requests


def run():
    try:
        # Your automation
        result = perform_automation()
        return result

    except Exception as e:
        # Send to Slack/Discord/Email
        requests.post(
            os.getenv("WEBHOOK_URL"),
            json={"text": f"Scheduled function failed: {str(e)}", "function_id": "function_abc123"},
        )

        raise  # Re-raise to mark run as failed
