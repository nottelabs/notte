"""Interrupt actual recipe processes while the SDK awaits a real owned claim."""

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import httpx


@unittest.skipUnless(os.getenv("NOTTE_VIBIUM_LIVE") == "1", "requires an explicitly selected Notte environment")
class CliTests(unittest.TestCase):
    def test_claim_sigint_and_sigterm_close_owned_browser(self):
        for language in ("python", "typescript"):
            for interrupt in (signal.SIGINT, signal.SIGTERM):
                with self.subTest(language=language, signal=interrupt.name):
                    self.check_claim(language, interrupt)

    def check_claim(self, language, interrupt):
        upstream = os.environ.get("NOTTE_API_URL", "https://api.notte.cc").rstrip("/")
        state = {"id": None, "interrupted": False, "child": None, "requests_after_claim": 0}
        journal = Path(
            os.environ.get(
                "VIBIUM_OWNERSHIP_JOURNAL", str(Path(tempfile.gettempdir()) / f"notte-vibium-owned-{os.getpid()}.jsonl")
            )
        )

        def record(event):
            # Persist the owned UUID before a signal or claim response can race cleanup.
            descriptor = os.open(journal, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(descriptor, "a", encoding="utf-8") as file:
                file.write(
                    json.dumps({"session_id": state["id"], "language": language, "signal": interrupt.name, **event})
                    + "\n"
                )
                file.flush()
                os.fsync(file.fileno())

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def forward(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                try:
                    headers = {
                        k: v
                        for k, v in self.headers.items()
                        if k.lower() not in {"host", "connection", "content-length"}
                    }
                    with httpx.Client(timeout=30, follow_redirects=False) as client:
                        response = client.request(self.command, upstream + self.path, headers=headers, content=body)
                    if self.command == "POST" and self.path == "/sessions/start" and response.is_success:
                        state["id"] = response.json().get("session_id")
                        if state["id"]:
                            record({"event": "allocated"})
                            state["child"].send_signal(interrupt)
                            state["interrupted"] = True
                            time.sleep(0.05)
                            state["child"].send_signal(interrupt)  # A repeated signal must not interrupt owner cleanup.
                            time.sleep(0.15)  # Both signals arrive before the native SDK receives its claim response.
                    elif state["id"] and urlsplit(self.path).path != f"/sessions/{state['id']}/stop":
                        state["requests_after_claim"] += 1
                    self.send_response(response.status_code)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(response.content)))
                    self.end_headers()
                    self.wfile.write(response.content)
                except Exception:
                    self.send_error(502, "Owned API proxy failed")

            do_POST = forward
            do_GET = forward
            do_DELETE = forward

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        child = None
        closed = False
        try:
            root = Path(__file__).parent
            command = [sys.executable, "demo.py"] if language == "python" else [shutil.which("node"), "src/demo.ts"]
            child = subprocess.Popen(
                command,
                cwd=root,
                env={**os.environ, "NOTTE_API_URL": f"http://127.0.0.1:{server.server_port}"},
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            state["child"] = child
            output = child.communicate(timeout=90)[0].decode(errors="replace")
            self.assertTrue(
                state["interrupted"], "The actual CLI must receive a signal after allocating its owned browser"
            )
            self.assertEqual(child.returncode, 130, "The recipe must finish graceful cancellation")
            self.assertEqual(state["requests_after_claim"], 0, "An aborted claim must not start browser actions")
            self.assertFalse(os.environ["NOTTE_API_KEY"] in output, "CLI output contained a credential")
        finally:
            if child and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            if state["id"]:
                print(f"Owned CLI browser: {state['id']} ({language}, {interrupt.name})", flush=True)
                headers = {"Authorization": f"Bearer {os.environ['NOTTE_API_KEY']}"}
                with httpx.Client(headers=headers, timeout=15, follow_redirects=False) as client:
                    deadline = time.monotonic() + 15
                    while time.monotonic() < deadline:
                        response = client.get(f"{upstream}/sessions/{state['id']}")
                        response.raise_for_status()
                        if response.json()["status"] == "closed":
                            closed = True
                            break
                        time.sleep(0.25)
                    if not closed:
                        stopped = client.delete(
                            f"{upstream}/sessions/{state['id']}/stop", params={"close_reason": "error"}
                        )
                        stopped.raise_for_status()
                        confirmed = client.get(f"{upstream}/sessions/{state['id']}")
                        confirmed.raise_for_status()
                        self.assertEqual(
                            confirmed.json()["status"], "closed", "Fallback must clean only the owned browser"
                        )
                print(
                    json.dumps(
                        {
                            "session_id": state["id"],
                            "language": language,
                            "signal": interrupt.name,
                            "recipe_closed": closed,
                        }
                    ),
                    flush=True,
                )
                record({"event": "closed", "recipe_closed": closed})
                self.assertTrue(closed, "Independent API status must confirm the recipe closed its owned browser")


if __name__ == "__main__":
    unittest.main()
