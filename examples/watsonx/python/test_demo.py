import base64
import json
import os
import unittest
from unittest.mock import patch

import requests
from demo import describe

PNG = b"\x89PNG\r\n\x1a\nfixture"
SETTINGS = {
    "WATSONX_URL": "https://us-south.ml.cloud.ibm.com",
    "WATSONX_API_KEY": "fixture-api-key",  # pragma: allowlist secret
    "WATSONX_PROJECT_ID": "fixture-project",
    "WATSONX_MODEL_ID": "fixture-model",
}


class Transport(requests.Session):
    def __init__(self, mode="fixture"):
        super().__init__()
        self.mode = mode
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = requests.Response()
        response.status_code = 200
        if len(self.calls) == 1:
            data = {"access_token": "fixture-bearer"}
            if self.mode == "invalid-token":
                data = {}
            elif self.mode in ["iam-reject", "redirect"]:
                response.status_code = 401 if self.mode == "iam-reject" else 302
                data = {"error": "PRIVATE_FIXTURE_BODY"}
        else:
            data = {"choices": [{"message": {"content": "Visible page description"}}]}
            if self.mode == "chat-reject":
                response.status_code = 403
                data = {"error": "PRIVATE_FIXTURE_BODY"}
            elif self.mode == "empty":
                data["choices"][0]["message"]["content"] = " "
        response._content = json.dumps(data).encode()
        return response


@patch.dict(os.environ, SETTINGS)
class WatsonxContract(unittest.TestCase):
    def test_iam_exchange_and_image_chat_contract(self):
        with Transport() as http:
            self.assertEqual(describe(PNG, http), "Visible page description")
        self.assertEqual(len(http.calls), 2)
        url, token = http.calls[0]
        self.assertEqual(url, "https://iam.cloud.ibm.com/identity/token")
        self.assertEqual(
            token["data"],
            {"grant_type": "urn:ibm:params:oauth:grant-type:apikey", "apikey": SETTINGS["WATSONX_API_KEY"]},
        )
        url, chat = http.calls[1]
        self.assertEqual(url, "https://us-south.ml.cloud.ibm.com/ml/v1/text/chat")
        self.assertEqual(chat["params"], {"version": "2024-05-31"})
        self.assertEqual(chat["headers"]["Authorization"], "Bearer fixture-bearer")
        body = chat["json"]
        self.assertEqual(
            (body["project_id"], body["model_id"], body["max_tokens"]), ("fixture-project", "fixture-model", 200)
        )
        image = body["messages"][0]["content"][1]["image_url"]["url"]
        self.assertEqual(base64.b64decode(image.split(",")[1]), PNG)
        for _, options in http.calls:
            self.assertEqual(options["timeout"], 30)
            self.assertIs(options["allow_redirects"], False)

    def test_regional_endpoint_accepts_a_trailing_slash(self):
        with patch.dict(os.environ, {"WATSONX_URL": "https://eu-de.ml.cloud.ibm.com/"}), Transport() as http:
            describe(PNG, http)
        self.assertEqual(http.calls[1][0], "https://eu-de.ml.cloud.ibm.com/ml/v1/text/chat")

    def test_failed_or_invalid_iam_never_sends_image(self):
        for mode in ["iam-reject", "invalid-token", "redirect"]:
            with self.subTest(mode=mode), Transport(mode) as http:
                with self.assertRaises((requests.HTTPError, RuntimeError)):
                    describe(PNG, http)
                self.assertEqual(len(http.calls), 1)

    def test_model_rejection_and_empty_result_fail(self):
        for mode in ["chat-reject", "empty"]:
            with self.subTest(mode=mode), Transport(mode) as http:
                with self.assertRaises((requests.HTTPError, RuntimeError)):
                    describe(PNG, http)


if __name__ == "__main__":
    unittest.main()
