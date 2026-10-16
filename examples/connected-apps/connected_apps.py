"""Discover Quaso connected apps with your workspace's Notte API key."""

import http.client
import json
import os
from typing import Any
from urllib.parse import urlencode


def request(api_key: str, path: str, body: dict[str, Any] | None = None) -> Any:
    connection = http.client.HTTPSConnection("www.quaso.ai", timeout=20)
    try:
        connection.request(
            "GET" if body is None else "POST",
            f"/api/integrations/{path}",
            body=None if body is None else json.dumps(body),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        response = connection.getresponse()
        if response.status != 200:
            raise RuntimeError(f"Connected apps request failed: HTTP {response.status}")
        return json.loads(response.read())
    finally:
        connection.close()


def discover(api_key: str, app: str = "github") -> dict[str, Any]:
    return {
        "apps": request(api_key, f"apps?{urlencode({'slug': app})}")["data"],
        "accounts": [
            account
            for account in request(api_key, "accounts")["data"]
            if (account.get("app") or {}).get("nameSlug") == app
        ],
        "actions": request(api_key, f"actions?{urlencode({'app': app, 'limit': 10})}")["data"],
    }


def run_action(api_key: str, account_id: str, action_key: str, configured_props: dict[str, Any]) -> Any:
    return request(
        api_key,
        "actions-run",
        {"accountId": account_id, "actionKey": action_key, "configuredProps": configured_props},
    )["result"]


if __name__ == "__main__":
    key = os.environ.get("NOTTE_API_KEY")
    if not key:
        raise SystemExit("Set NOTTE_API_KEY for your Quaso workspace")
    result = discover(key, os.environ.get("CONNECTED_APP", "github"))
    print(json.dumps({name: len(items) for name, items in result.items()}))
