from notte_sdk import NotteClient


def test_functions_get_curl_uses_functions_endpoint() -> None:
    client = NotteClient(api_key="test-api-key", server_url="https://api.notte.cc")

    curl = client.functions.get_curl(function_id="function-123", query="hello")

    assert "https://api.notte.cc/functions/function-123/runs/start" in curl
    assert "/workflows/" not in curl
