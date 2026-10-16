import base64
import hashlib
import json
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from proposal import MAP_PATH, apply_proposal
from publish import publish

SOURCE = Path(__file__).with_name("selectors.json").read_bytes()
SHA = "a" * 40


def proposal():
    return {
        "version": 1,
        "source_sha256": hashlib.sha256(SOURCE).hexdigest(),
        "session_id": "12345678-1234-1234-1234-123456789abc",
        "changes": [
            {"key": "learn_more", "before": ".outdated-learn-more", "after": 'a[href="https://example.com/docs"]'}
        ],
    }


@contextmanager
def github(mode="success"):
    state = {"requests": [], "branch": False, "updated": SOURCE, "pr": False}
    if mode == "unrelated":
        state.update(
            branch=True,
            updated=apply_proposal(
                SOURCE, json.dumps(proposal()).encode(), hashlib.sha256(json.dumps(proposal()).encode()).hexdigest()
            ),
        )

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def handle_request(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            body = json.loads(raw) if raw else None
            state["requests"].append((self.command, self.path, dict(self.headers), body))
            if mode == "401":
                return self.reply({"message": "private fixture-token details"}, 401)
            if mode == "redirect":
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/redirect-target")
                self.send_header("Content-Length", "0")
                return self.end_headers()
            path = urlsplit(self.path)
            route = path.path.removeprefix("/repos/fixture/repository")
            if route == "/git/ref/heads/main":
                return self.reply({"object": {"sha": "d" * 40 if mode == "moved" else SHA}})
            if route.startswith("/git/ref/heads/"):
                return self.reply(
                    {"object": {"sha": "c" * 40 if state["updated"] != SOURCE else SHA}},
                    200 if state["branch"] else 404,
                )
            if route == "/git/refs":
                state["branch"] = True
                return self.reply({"ref": body["ref"], "object": {"sha": SHA}}, 201)
            if route == "/contents/" + MAP_PATH:
                if self.command == "PUT":
                    state["updated"] = base64.b64decode(body["content"])
                    return self.reply({"content": {"sha": "e" * 40}}, 200)
                ref = parse_qs(path.query)["ref"][0]
                data = SOURCE if ref == SHA else state["updated"]
                return self.reply(
                    {"type": "file", "encoding": "base64", "sha": "b" * 40, "content": base64.b64encode(data).decode()}
                )
            if route.startswith("/compare/"):
                return self.reply(
                    {
                        "ahead_by": 1,
                        "behind_by": 0,
                        "files": [{"filename": MAP_PATH}, *([{"filename": "other.py"}] if mode == "unrelated" else [])],
                        "commits": [{"parents": [{"sha": SHA}]}],
                    }
                )
            if route == "/pulls":
                if self.command == "POST":
                    state["pr"] = True
                    return self.reply({"html_url": "https://github.com/fixture/repository/pull/1"}, 201)
                return self.reply([{"html_url": "https://github.com/fixture/repository/pull/1"}] if state["pr"] else [])
            return self.reply({}, 404)

        def reply(self, value, status=200):
            raw = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        do_GET = handle_request
        do_POST = handle_request
        do_PUT = handle_request

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def execute(api_url, value=None, digest=None):
    raw = json.dumps(proposal() if value is None else value).encode()
    return publish(
        SOURCE,
        raw,
        digest or hashlib.sha256(raw).hexdigest(),
        repository="fixture/repository",
        base="main",
        source_sha=SHA,
        run_id="123",
        token="fixture-token",
        api_url=api_url,
    )


class PublishTests(unittest.TestCase):
    def test_native_github_protocol_and_retry_deduplication(self):
        with github() as (url, state):
            self.assertEqual(execute(url), "https://github.com/fixture/repository/pull/1")
            self.assertEqual(execute(url), "https://github.com/fixture/repository/pull/1")
            writes = [item for item in state["requests"] if item[0] != "GET"]
            self.assertEqual([method for method, *_ in writes], ["POST", "PUT", "POST"])
            self.assertEqual(writes[0][3], {"ref": "refs/heads/notte-selector-repair-123", "sha": SHA})
            self.assertEqual(writes[1][1], "/repos/fixture/repository/contents/" + MAP_PATH)
            self.assertEqual(writes[1][3]["sha"], "b" * 40)
            self.assertEqual(writes[2][3]["draft"], True)
            before, after = json.loads(SOURCE), json.loads(state["updated"])
            before["selectors"]["learn_more"]["selector"] = after["selectors"]["learn_more"]["selector"]
            self.assertEqual(before, after, "Only the fixed selector field may change")
            for _, _, headers, _ in state["requests"]:
                self.assertEqual(headers["Authorization"], "Bearer fixture-token")
                self.assertEqual(headers["X-Github-Api-Version"], "2026-03-10")

    def test_stale_commit_or_unrelated_branch_never_writes(self):
        for mode in ["moved", "unrelated"]:
            with self.subTest(mode=mode), github(mode) as (url, state):
                with self.assertRaises(RuntimeError):
                    execute(url)
                self.assertTrue(all(item[0] == "GET" for item in state["requests"]))

    def test_invalid_or_substituted_artifact_never_contacts_github(self):
        with github() as (url, state):
            invalid = []
            value = proposal()
            value["path"] = "../../other.py"
            invalid.append(value)
            value = proposal()
            value["changes"][0]["key"] = "../../other.py"
            invalid.append(value)
            value = proposal()
            value["source_sha256"] = "0" * 64
            invalid.append(value)
            value = proposal()
            value["changes"][0]["before"] = "other"
            invalid.append(value)
            for value in invalid:
                with self.subTest(value=value), self.assertRaises(ValueError):
                    execute(url, value)
            with self.assertRaises(ValueError):
                execute(url, digest="0" * 64)
            self.assertEqual(state["requests"], [])

    def test_http_errors_are_sanitized_and_redirects_never_forward_credentials(self):
        for mode in ["401", "redirect"]:
            with self.subTest(mode=mode), github(mode) as (url, state):
                with self.assertRaisesRegex(RuntimeError, "GitHub HTTP") as error:
                    execute(url)
                self.assertNotIn("fixture-token", str(error.exception))
                self.assertEqual(len(state["requests"]), 1)

    def test_no_change_proposal_makes_no_external_request(self):
        value = proposal()
        value["changes"] = []
        with github() as (url, state):
            self.assertIsNone(execute(url, value))
            self.assertEqual(state["requests"], [])


if __name__ == "__main__":
    unittest.main()
