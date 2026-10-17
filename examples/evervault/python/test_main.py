import asyncio
import base64
import json
import os
import signal
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from main import CA_SHA256, Notte, create_token, disconnect, fill_password
from playwright.async_api import async_playwright

ID = "11111111-1111-4111-8111-111111111111"
TARGET = "https://login.example.test/form"
PROXY = {
    "type": "external",
    "server": "https://us-va.browser.relay.evervault.app:443",
    "username": "fixture-app",
    "password": "fixture-proxy-jwe",  # pragma: allowlist secret (dummy fixture)
}
MARKERS = {"X-Notte-Browser-Trust-Profile": "evervault", "X-Notte-Browser-Trust-SHA256": CA_SHA256}


def fixture(headers=None, vendor_status=200, start_status=200):
    requests = []

    async def handler(request):
        requests.append(request)
        if request.url.path == "/browser-tokens":
            return httpx.Response(
                vendor_status,
                json={
                    "data": [
                        {"category": "credential.password", "id": "login-password", "value": "fixture-browser-token"}
                    ],
                    "proxyConfiguration": {
                        "hostname": "us-va.browser.relay.evervault.app",
                        "port": 443,
                        "username": PROXY["username"],
                        "password": PROXY["password"],
                    },
                    "expiresAt": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
                },
            )
        if request.url.path == "/sessions/start":
            return httpx.Response(
                start_status,
                headers=MARKERS if headers is None else headers,
                json={"session_id": ID, "cdp_url": "wss://cdp.example.test/fixture"},
            )
        if request.url.path.endswith("/stop"):
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"status": "closed"})

    return requests, httpx.MockTransport(handler)


def browser_fixture(fail=False):
    fill = AsyncMock()
    page = SimpleNamespace(
        url=TARGET,
        goto=AsyncMock(side_effect=RuntimeError(PROXY["password"]) if fail else None),
        locator=lambda _: SimpleNamespace(fill=fill),
    )
    browser = SimpleNamespace(contexts=[SimpleNamespace(new_page=AsyncMock(return_value=page))], close=AsyncMock())
    return browser, fill, AsyncMock(return_value=browser)


async def test_contracts_keep_encrypted_input_and_vendor_credentials_out_of_notte():
    requests, transport = fixture()
    browser, fill, connect = browser_fixture()
    token, proxy = await create_token("fixture-app", "fixture-evervault-key", "ev:fixture-encrypted", TARGET, transport)
    notte = Notte("fixture-notte-key", transport=transport)
    try:
        assert await fill_password(notte, proxy, token, TARGET, connect) == {"session_id": ID, "filled": True}
        vendor, start, stop, status = requests
        assert (
            vendor.headers["Authorization"]
            == "Basic " + base64.b64encode(b"fixture-app:fixture-evervault-key").decode()
        )
        assert json.loads(vendor.content)["permissions"] == [{"action": "decrypt", "target": "login.example.test"}]
        assert json.loads(vendor.content)["ttl"] == 300
        assert json.loads(start.content)["proxies"] == [PROXY]
        assert json.loads(start.content)["browser_trust_profile"] == "evervault"
        assert b"ev:fixture-encrypted" not in start.content and b"fixture-evervault-key" not in start.content
        assert start.headers["Authorization"] == "Bearer fixture-notte-key"
        fill.assert_awaited_once_with("fixture-browser-token", timeout=15_000)
        browser.close.assert_awaited_once()
        assert stop.method == "DELETE" and status.url.path == f"/sessions/{ID}"
        connect.assert_awaited_once_with("wss://cdp.example.test/fixture", timeout=30_000)
    finally:
        await notte.http.aclose()


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {**MARKERS, "X-Notte-Browser-Trust-SHA256": "wrong"},
        {"X-Notte-Browser-Trust-Profile": "evervault"},
        {"X-Notte-Browser-Trust-SHA256": CA_SHA256},
    ],
)
async def test_missing_or_mismatched_trust_closes_before_cdp(headers):
    requests, transport = fixture(headers)
    notte = Notte("fixture-key", transport=transport)
    _, _, connect = browser_fixture()
    try:
        with pytest.raises(RuntimeError, match="trust was not verified"):
            await fill_password(notte, PROXY, "fixture-token", TARGET, connect)
        connect.assert_not_awaited()
        assert [r.method for r in requests] == ["POST", "DELETE", "GET"]
    finally:
        await notte.http.aclose()


async def test_browser_failure_redacts_cause_and_closes():
    requests, transport = fixture()
    notte = Notte("fixture-key", transport=transport)
    browser, _, connect = browser_fixture(True)
    try:
        with pytest.raises(RuntimeError, match="^Browser token form fill failed$"):
            await fill_password(notte, PROXY, "fixture-token", TARGET, connect)
        browser.close.assert_awaited_once()
        assert [r.method for r in requests] == ["POST", "DELETE", "GET"]
    finally:
        await notte.http.aclose()


@pytest.mark.parametrize("target", ["https://LOGIN.example.test/form", "https://login.example.test:443/form"])
async def test_browser_normalized_origin_still_fills_the_owned_form(target):
    _, transport = fixture()
    notte = Notte("fixture-key", transport=transport)
    _, fill, connect = browser_fixture()
    try:
        await fill_password(notte, PROXY, "fixture-token", target, connect)
        fill.assert_awaited_once_with("fixture-token", timeout=15_000)
    finally:
        await notte.http.aclose()


@pytest.mark.parametrize("target", ["https://different.example.test/form", "https://login.example.test:444/form"])
async def test_different_origin_is_never_filled_and_owned_browser_closes(target):
    requests, transport = fixture()
    notte = Notte("fixture-key", transport=transport)
    browser, fill, connect = browser_fixture()
    try:
        with pytest.raises(RuntimeError, match="^Browser token form fill failed$"):
            await fill_password(notte, PROXY, "fixture-token", target, connect)
        fill.assert_not_awaited()
        browser.close.assert_awaited_once()
        assert [request.method for request in requests] == ["POST", "DELETE", "GET"]
    finally:
        await notte.http.aclose()


async def test_cancel_during_start_recovers_owned_id_and_closes():
    requests, transport = fixture()
    notte = Notte("fixture-key", transport=transport)
    started, release = asyncio.Event(), asyncio.Event()
    original = notte.request

    async def delayed(method, path, **kwargs):
        if path == "/sessions/start":
            started.set()
            await release.wait()
        return await original(method, path, **kwargs)

    notte.request = delayed

    async def run():
        async with notte.owned({}):
            pytest.fail("Cancelled caller reached browser work")

    task = asyncio.create_task(run())
    try:
        await started.wait()
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert [r.method for r in requests] == ["POST", "DELETE", "GET"]
    finally:
        await notte.http.aclose()


@pytest.mark.parametrize("phase", ["DELETE", "GET"])
async def test_repeated_cancellation_during_cleanup_finishes_then_propagates(phase):
    requests, transport = fixture()
    notte = Notte("fixture-key", transport=transport)
    entered, release = asyncio.Event(), asyncio.Event()
    original = notte.request

    async def delayed(method, path, **kwargs):
        if method == phase:
            entered.set()
            await release.wait()
        return await original(method, path, **kwargs)

    notte.request = delayed

    async def run():
        async with notte.owned({}):
            pass

    task = asyncio.create_task(run())
    try:
        await entered.wait()
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done(), "Caller cancellation interrupted owned cleanup"
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 3)
        assert [request.method for request in requests] == ["POST", "DELETE", "GET"]
    finally:
        release.set()
        await notte.http.aclose()


async def test_vendor_auth_failure_does_not_return_response_body():
    _, transport = fixture(vendor_status=401)
    with pytest.raises(RuntimeError, match="^Evervault returned HTTP 401$"):
        await create_token("app", "key", "ev:fixture", TARGET, transport)


async def test_http_deadline_bounds_a_server_that_never_finishes():
    async def hang(_):
        await asyncio.Event().wait()

    notte = Notte("fixture-key", transport=httpx.MockTransport(hang))
    try:
        with pytest.raises(RuntimeError, match=r"^Notte transport failed \(TimeoutError\)$"):
            await notte.request("GET", "/health", timeout=0.01)
    finally:
        await notte.http.aclose()


async def test_failed_start_with_owned_id_still_closes_before_cdp():
    requests, transport = fixture(start_status=502)
    notte = Notte("fixture-key", transport=transport)
    _, _, connect = browser_fixture()
    try:
        with pytest.raises(RuntimeError, match=r"^Notte start failed \(HTTP 502\)$"):
            await fill_password(notte, PROXY, "fixture-token", TARGET, connect)
        connect.assert_not_awaited()
        assert [r.method for r in requests] == ["POST", "DELETE", "GET"]
    finally:
        await notte.http.aclose()


async def test_cancellation_during_browser_action_disconnects_and_closes():
    requests, transport = fixture()
    notte = Notte("fixture-key", transport=transport)
    browser, _, connect = browser_fixture()
    entered = asyncio.Event()

    async def wait(*_, **__):
        entered.set()
        await asyncio.Event().wait()

    browser.contexts[0].new_page.return_value.goto.side_effect = wait
    task = asyncio.create_task(fill_password(notte, PROXY, "fixture-token", TARGET, connect))
    try:
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        browser.close.assert_awaited_once()
        assert [r.method for r in requests] == ["POST", "DELETE", "GET"]
    finally:
        await notte.http.aclose()


async def test_unresponsive_cdp_close_cannot_prevent_owned_stop_and_get_closed():
    requests, transport = fixture()
    notte = Notte("fixture-key", transport=transport)
    browser, _, connect = browser_fixture()

    async def hang():
        await asyncio.Event().wait()

    browser.close.side_effect = hang
    try:
        with pytest.raises(RuntimeError, match="^Browser disconnect failed$"):
            await asyncio.wait_for(fill_password(notte, PROXY, "fixture-token", TARGET, connect), 8)
        assert [r.method for r in requests] == ["POST", "DELETE", "GET"]
    finally:
        await notte.http.aclose()


@pytest.mark.parametrize("termination", [signal.SIGTERM, signal.SIGINT])
async def test_native_cli_signal_during_startup_recovers_response_and_closes(termination):
    entered, release = threading.Event(), threading.Event()
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, data, headers=None):
            body = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            requests.append(("POST", self.path))
            entered.set()
            release.wait(45)
            self.reply({"session_id": ID}, MARKERS)

        def do_DELETE(self):
            requests.append(("DELETE", self.path))
            self.reply({})

        def do_GET(self):
            requests.append(("GET", self.path))
            self.reply({"status": "closed"})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    script = (
        "import asyncio\nfrom main import main\nasync def tokens(*_):\n return 'fixture-token', "
        + repr(PROXY)
        + "\ntry:\n asyncio.run(main(tokens))\nexcept (asyncio.CancelledError, KeyboardInterrupt):\n raise SystemExit(1) from None\n"
    )
    child = subprocess.Popen(
        [sys.executable, "-c", script],
        env={
            "PATH": os.environ.get("PATH", ""),
            "NOTTE_API_KEY": "fixture-notte-key",  # pragma: allowlist secret (dummy fixture)
            "NOTTE_API_URL": f"http://127.0.0.1:{server.server_port}",
            "EVERVAULT_APP_ID": "fixture-app",
            "EVERVAULT_API_KEY": "fixture-vendor-key",  # pragma: allowlist secret (dummy fixture)
            "EVERVAULT_ENCRYPTED_PASSWORD": "ev:fixture",  # pragma: allowlist secret (dummy fixture)
            "EVERVAULT_FORM_URL": TARGET,
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert await asyncio.to_thread(entered.wait, 45), "CLI did not reach startup"
        child.send_signal(termination)
        await asyncio.sleep(0.1)
        release.set()
        await asyncio.to_thread(child.communicate, timeout=15)
        assert child.returncode not in (0, -termination), "CLI terminated without graceful task cancellation"
        assert requests == [("POST", "/sessions/start"), ("DELETE", f"/sessions/{ID}/stop"), ("GET", f"/sessions/{ID}")]
    finally:
        release.set()
        if child.poll() is None:
            child.kill()
            await asyncio.to_thread(child.communicate, timeout=5)
        await asyncio.to_thread(server.shutdown)
        server.server_close()
        thread.join(timeout=2)


async def test_plaintext_is_rejected_before_vendor_request():
    with pytest.raises(ValueError, match="encrypted value"):
        await create_token("app", "key", "plaintext", TARGET)


LIVE = os.environ.get("NOTTE_EVERVAULT_LIVE") == "1"


class ObservedNotte(Notte):
    async def close(self, session_id):
        await super().close(session_id)
        print(f"Owned browser closed: {session_id}")


@pytest.mark.skipif(not LIVE, reason="Set NOTTE_EVERVAULT_LIVE=1")
async def test_live_notte_browser_control_fills_owned_dummy_form_and_closes():
    notte = ObservedNotte(os.environ["NOTTE_API_KEY"], os.environ.get("NOTTE_API_URL", "https://api.notte.cc"))
    try:
        async with notte.owned({"max_duration_minutes": 3, "proxies": False}, trust=False) as (_, cdp):
            async with async_playwright() as playwright:
                browser = await playwright.chromium.connect_over_cdp(await cdp(), timeout=30_000)
                try:
                    page = await browser.contexts[0].new_page()
                    await page.goto("https://example.com", wait_until="domcontentloaded")
                    await page.set_content('<form><input name="password" type="password"></form>')
                    await page.locator('[name="password"]').fill("fixture-browser-token")
                    assert await page.locator('[name="password"]').input_value() == "fixture-browser-token"
                finally:
                    await disconnect(browser)
    finally:
        await notte.http.aclose()


@pytest.mark.skipif(not LIVE, reason="Set NOTTE_EVERVAULT_LIVE=1")
async def test_live_unknown_profile_never_hands_out_cdp_and_closes_returned_id():
    notte = ObservedNotte(os.environ["NOTTE_API_KEY"], os.environ.get("NOTTE_API_URL", "https://api.notte.cc"))
    try:
        with pytest.raises(
            RuntimeError, match=r"trust was not verified|Notte start returned no owned ID \(HTTP (400|422)\)"
        ):
            async with notte.owned(
                {"max_duration_minutes": 3, "proxies": False, "browser_trust_profile": "__unknown_profile__"}
            ):
                pytest.fail("Unverified profile reached browser work")
    finally:
        await notte.http.aclose()


@pytest.mark.skipif(
    os.environ.get("NOTTE_EVERVAULT_PROFILE_LIVE") != "1", reason="Explicit supported-profile acceptance only"
)
async def test_explicit_supported_profile_acceptance_verifies_runtime_without_vendor_credentials():
    notte = ObservedNotte(os.environ["NOTTE_API_KEY"], os.environ.get("NOTTE_API_URL", "https://api.notte.cc"))
    try:
        async with notte.owned({"max_duration_minutes": 3, "proxies": False, "browser_trust_profile": "evervault"}) as (
            _,
            cdp,
        ):
            async with async_playwright() as playwright:
                browser = await playwright.chromium.connect_over_cdp(await cdp(), timeout=30_000)
                try:
                    page = await browser.contexts[0].new_page()
                    await page.goto("https://example.com", wait_until="domcontentloaded")
                    assert await page.title() == "Example Domain"
                    await page.set_content('<form><input name="password" type="password"></form>')
                    await page.locator('[name="password"]').fill("fixture-browser-token")
                    assert await page.locator('[name="password"]').input_value() == "fixture-browser-token"
                finally:
                    await disconnect(browser)
    finally:
        await notte.http.aclose()
