import asyncio
import gzip
import json
import os
import re
import subprocess
import sys
import threading
import time
import unittest
import urllib.request
import uuid
from contextlib import asynccontextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import read_page
from lmnr import Laminar
from notte_sdk import NotteClient
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

LIVE = os.getenv("NOTTE_LAMINAR_LIVE") == "1"


async def closed(client, session_id):
    for _ in range(30):
        status = await asyncio.to_thread(client.sessions.status, session_id)
        if status.status == "closed":
            return
        await asyncio.sleep(0.5)
    raise AssertionError("The owned browser session did not close")


@asynccontextmanager
async def owned():
    if not os.getenv("NOTTE_API_URL"):
        raise AssertionError("Choose the browser API explicitly")
    client, ids = NotteClient(), []
    original = client.sessions.start

    def start(**kwargs):
        response = original(**kwargs)
        ids.append(response.session_id)
        return response

    try:
        with (
            patch.object(client.sessions, "start", side_effect=start),
            patch.object(read_page, "NotteClient", return_value=client),
        ):
            yield ids
    finally:
        for session_id in ids:
            await closed(client, session_id)
        if len(ids) != 1:
            raise AssertionError("The example must own exactly one session")


@unittest.skipUnless(LIVE, "Opt-in cloud browser and trace tests")
class LaminarTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.payloads = []

        class Collector(BaseHTTPRequestHandler):
            def do_POST(self):
                payload = self.rfile.read(int(self.headers["Content-Length"]))
                if self.headers.get("Content-Encoding") == "gzip":
                    payload = gzip.decompress(payload)
                cls.payloads.append(ExportTraceServiceRequest.FromString(payload))
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *_):
                pass

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Collector)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        Laminar.initialize(
            project_api_key="integration-test-not-a-real-key",  # pragma: allowlist secret
            base_url="http://127.0.0.1",
            http_port=cls.server.server_port,
            instruments=set(),
            force_http=True,
        )

    @classmethod
    def tearDownClass(cls):
        Laminar.shutdown()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    async def emitted(self, offset):
        await asyncio.to_thread(Laminar.flush)
        spans = [
            span
            for payload in self.payloads[offset:]
            for resource in payload.resource_spans
            for scope in resource.scope_spans
            for span in scope.spans
            if span.name == "notte.read_page"
        ]
        self.assertEqual(len(spans), 1)
        payload = spans[0].SerializeToString()
        for value in [os.environ["NOTTE_API_KEY"], "integration-test-not-a-real-key"]:
            self.assertFalse(value.encode() in payload, "Trace payload contained a credential")
        return spans[0], payload

    async def test_browser_result_is_traced_and_session_closes(self):
        offset = len(self.payloads)
        async with owned() as ids:
            result = await read_page.read_page()
            self.assertEqual(result["title"], "Example Domain")
            self.assertEqual(ids, [result["session_id"]])
        span, payload = await self.emitted(offset)
        self.assertEqual(span.trace_id.hex(), result["trace_id"])
        self.assertIn(span.status.code, [0, 1])
        self.assertIn(b"Example Domain", payload)
        self.assertIn(ids[0].encode(), payload)

    async def test_navigation_failure_is_traced_and_session_closes(self):
        offset = len(self.payloads)
        async with owned() as ids:
            with self.assertRaisesRegex(
                RuntimeError, r"failed during navigation \(session [0-9a-f-]{36}, trace [0-9a-f]{32}\)"
            ):
                await read_page.read_page("http://127.0.0.1:1")
        span, payload = await self.emitted(offset)
        self.assertEqual(span.status.code, 2)
        self.assertIn(b"failed during navigation", payload)
        self.assertIn(ids[0].encode(), payload)

    @unittest.skipUnless(os.getenv("NOTTE_LAMINAR_EXPORT_LIVE") == "1", "Opt-in actual Laminar export and readback")
    async def test_trace_is_persisted_in_laminar(self):
        self.assertTrue(os.getenv("LMNR_PROJECT_API_KEY"))
        child = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, str(Path(__file__).with_name("read_page.py"))],
            capture_output=True,
            text=True,
            timeout=150,
        )
        if child.returncode:
            raise AssertionError("Laminar CLI failed; child output withheld")
        result = json.loads(next(line for line in reversed(child.stdout.splitlines()) if line.startswith('{"title"')))
        await closed(NotteClient(), result["session_id"])
        span = await self.persisted(result["trace_id"])
        output = span["output"]
        if isinstance(output, str):
            output = json.loads(output)
        self.assertEqual(output["title"], "Example Domain")
        self.assertEqual(output["session_id"], result["session_id"])

    @unittest.skipUnless(os.getenv("NOTTE_LAMINAR_EXPORT_LIVE") == "1", "Opt-in actual Laminar export and readback")
    async def test_failed_trace_is_persisted_in_laminar(self):
        child = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, str(Path(__file__).with_name("read_page.py")), "http://127.0.0.1:1"],
            capture_output=True,
            text=True,
            timeout=150,
        )
        self.assertNotEqual(child.returncode, 0)
        match = re.search(r"failed during navigation \(session ([0-9a-f-]{36}), trace ([0-9a-f]{32})\)", child.stderr)
        self.assertTrue(match, "Child did not report the owned session and trace")
        session_id, trace_id = match.groups()
        await closed(NotteClient(), session_id)
        span = await self.persisted(trace_id)
        payload = json.dumps(span)
        self.assertIn("failed during navigation", payload)
        self.assertIn(session_id, payload)
        self.assertFalse(os.environ["NOTTE_API_KEY"] in payload, "Stored span contained a credential")

    async def persisted(self, trace_hex):
        trace_id = str(uuid.UUID(hex=trace_hex))
        query = f"SELECT * FROM spans WHERE trace_id = '{trace_id}' LIMIT 5"
        request = urllib.request.Request(
            os.getenv("LMNR_BASE_URL", "https://api.lmnr.ai").rstrip("/") + "/v1/sql/query",
            data=json.dumps({"query": query, "parameters": {}}).encode(),
            headers={
                "Authorization": f"Bearer {os.environ['LMNR_PROJECT_API_KEY']}",
                "Content-Type": "application/json",
            },
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:

            def fetch():
                with urllib.request.urlopen(request, timeout=min(10, max(1, deadline - time.monotonic()))) as response:
                    return json.load(response).get("data", [])

            rows = await asyncio.to_thread(fetch)
            matches = [row for row in rows if row.get("name") == "notte.read_page"]
            if matches:
                return matches[0]
            await asyncio.sleep(0.5)
        self.fail("The exported trace did not appear in Laminar")


if __name__ == "__main__":
    unittest.main()
