import http.client
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from connected_apps import discover, run_action


class ConnectedAppsTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.status = 200
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                self.handle_request()

            def do_POST(self):
                self.handle_request()

            def handle_request(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                owner.calls.append((self.command, self.path, self.headers.get("Authorization"), body))
                data = {"error": "private fixture detail"}
                if "/apps?" in self.path:
                    data = {"data": [{"nameSlug": "github", "authType": "oauth"}]}
                elif self.path.endswith("/accounts"):
                    data = {
                        "data": [
                            {"id": "owned", "healthy": True, "app": {"nameSlug": "github"}},
                            {"id": "other", "app": {"nameSlug": "gmail"}},
                            {"id": "unknown", "app": None},
                        ]
                    }
                elif "/actions?" in self.path:
                    data = {"data": [{"key": "github-get-user", "name": "Get user"}]}
                elif self.path.endswith("/actions-run"):
                    data = {"ok": True, "result": {"ret": {"login": "fixture-user"}}}
                self.send_response(owner.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Location", "/unexpected-redirect")
                self.end_headers()
                self.wfile.write(json.dumps(data).encode())

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.connection = patch("connected_apps.http.client.HTTPSConnection", self.connect)
        self.connection.start()
        self.addCleanup(self.connection.stop)

    def connect(self, host, *, timeout):
        self.assertEqual(host, "www.quaso.ai")
        self.assertEqual(timeout, 20)
        return http.client.HTTPConnection(*self.server.server_address, timeout=timeout)

    def test_discovery_preserves_auth_and_filters_accounts(self):
        result = discover("fixture-token")
        self.assertEqual([account["id"] for account in result["accounts"]], ["owned"])
        self.assertEqual(result["actions"][0]["key"], "github-get-user")
        self.assertEqual(
            [call[1] for call in self.calls],
            [
                "/api/integrations/apps?slug=github",
                "/api/integrations/accounts",
                "/api/integrations/actions?app=github&limit=10",
            ],
        )
        self.assertTrue(all(call[0] == "GET" and call[2] == "Bearer fixture-token" for call in self.calls))

    def test_read_only_action_contract(self):
        result = run_action("fixture-token", "owned", "github-get-user", {"username": "fixture-user"})
        self.assertEqual(result["ret"]["login"], "fixture-user")
        method, path, auth, body = self.calls[0]
        self.assertEqual((method, path, auth), ("POST", "/api/integrations/actions-run", "Bearer fixture-token"))
        self.assertEqual(
            json.loads(body),
            {"accountId": "owned", "actionKey": "github-get-user", "configuredProps": {"username": "fixture-user"}},
        )

    def test_http_error_reports_status_without_response_body(self):
        self.status = 401
        with self.assertRaisesRegex(RuntimeError, "HTTP 401") as error:
            discover("fixture-token")
        self.assertNotIn("private fixture detail", str(error.exception))
        self.assertEqual(len(self.calls), 1)

    def test_redirect_is_not_followed(self):
        self.status = 302
        with self.assertRaisesRegex(RuntimeError, "HTTP 302"):
            discover("fixture-token")
        self.assertEqual(len(self.calls), 1)


if __name__ == "__main__":
    unittest.main()
