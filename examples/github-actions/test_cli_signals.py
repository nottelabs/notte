"""Exercise the actual CLI and installed SDK against a delayed local API reply."""

import json
import os
import signal
import subprocess
import sys
import threading
import time
import unittest
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class SignalTests(unittest.TestCase):
    def run_cli(self, sig=None, count=1):
        started = threading.Event()
        release = threading.Event()
        stopped = threading.Event()
        now = datetime.now(timezone.utc).isoformat()
        response = {
            "session_id": "00000000-0000-4000-8000-000000000001",
            "idle_timeout_minutes": 3,
            "created_at": now,
            "last_accessed_at": now,
            "status": "active",
        }

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def reply(self, status, value):
                raw = json.dumps(value).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                if self.path.split("?")[0] != "/sessions/start":
                    self.reply(404, {})
                    return
                if sig is None:
                    self.reply(401, {"detail": "Fixture unauthorized"})
                    return
                started.set()
                release.wait(15)
                self.reply(200, response)

            def do_DELETE(self):
                if self.path.split("?")[0] != f"/sessions/{response['session_id']}/stop":
                    self.reply(404, {})
                    return
                stopped.set()
                self.reply(200, {**response, "status": "closed"})

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        env = {
            name: os.environ[name]
            for name in ("PATH", "HOME", "TMPDIR", "TEMP", "TMP", "NOTTE_ENABLE_NEST_ASYNCIO")
            if name in os.environ
        }
        env.update(dict.fromkeys(("NOTTE_API_KEY",), "fixture-local-only"))
        env["NOTTE_API_URL"] = f"http://127.0.0.1:{server.server_port}"
        child = subprocess.Popen(
            [sys.executable, str(Path(__file__).with_name("repair.py"))],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        try:
            if sig is not None:
                self.assertTrue(started.wait(15), "The real SDK must issue its claim before interruption")
                for _ in range(count):
                    child.send_signal(sig)
                    time.sleep(0.15)
                release.set()
            _output, _ = child.communicate(timeout=20)
            return child.returncode, stopped.is_set()
        finally:
            release.set()
            if child.poll() is None:
                child.kill()  # Fixture-only API: no real browser or account exists.
                child.communicate()
            server.shutdown()
            server.server_close()

    def test_single_and_repeated_signals_reap_the_delayed_claim(self):
        for sig, expected in ((signal.SIGINT, 130), (signal.SIGTERM, 143)):
            for count in (1, 2):
                with self.subTest(signal=sig.name, count=count):
                    code, stopped = self.run_cli(sig, count)
                    self.assertEqual(code, expected)
                    self.assertTrue(stopped, "Repeated signals must not cancel native SDK entry cleanup")

    def test_application_errors_keep_their_failure_exit(self):
        code, stopped = self.run_cli()
        self.assertEqual(code, 1)
        self.assertFalse(stopped, "A refused claim allocates no session")


if __name__ == "__main__":
    unittest.main()
