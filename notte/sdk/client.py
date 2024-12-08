import os

import requests
from notte.actions.base import Action
from notte.browser.context import Observation

URL = "https://api.notte.cc/v1"


class NotteClient:
    def __init__(self, token: str | None = None):
        self.token = token or os.getenv("NOTTE_TOKEN")
        if self.token is None:
            raise ValueError("No token provided")

    def observe(self, url: str) -> Observation:
        headers = {"Authorization": f"Bearer {self.token}"}
        response = requests.get(f"{URL}/observe", headers=headers, json={"url": url})
        return Observation.from_json(response.json())

    def step(
        self, action: Action | str, value: str | None = None, list_next: bool = True
    ) -> Observation:
        headers = {"Authorization": f"Bearer {self.token}"}
        response = requests.post(
            f"{URL}/step",
            headers=headers,
            json={"action": action, "value": value, "list_next": list_next},
        )
        return Observation.from_json(response.json())

    def chat(self, text: str) -> str:
        headers = {"Authorization": f"Bearer {self.token}"}
        response = requests.post(f"{URL}/chat", headers=headers, json={"text": text})
        return response.json()
