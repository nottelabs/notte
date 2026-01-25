# @sniptest filename=environment_variables.py
import os

from notte_sdk import NotteClient


def run():
    # Access environment variables
    api_key = os.getenv("MY_API_KEY")
    webhook_url = os.getenv("WEBHOOK_URL")

    if not api_key:
        return {"error": "API key not configured"}

    # Use in automation
    client = NotteClient(api_key=api_key)
