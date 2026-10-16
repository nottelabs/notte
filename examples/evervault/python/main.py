import asyncio
import os
import re
import signal
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from playwright.async_api import async_playwright

CA_SHA256 = "4137d69968b54bcf27de628e80cbe2535a15604af8b5ed1236831c9285365968"  # pragma: allowlist secret (public CA fingerprint)


class Notte:
    def __init__(self, key, root="https://api.notte.cc", transport=None):
        parsed = urlparse(root)
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname == "127.0.0.1"):
            raise ValueError("Use an HTTPS Notte API URL")
        self.http = httpx.AsyncClient(
            base_url=root,
            headers={"Authorization": f"Bearer {key}"},
            timeout=30,
            follow_redirects=False,
            transport=transport,
        )

    async def request(self, method, path, **kwargs):
        try:
            return await self.http.request(method, path, **kwargs)
        except Exception as error:
            raise RuntimeError(f"Notte transport failed ({type(error).__name__})") from None

    async def close(self, session_id):
        async with asyncio.timeout(15):
            stopped = await self.request("DELETE", f"/sessions/{session_id}/stop")
            if not stopped.is_success:
                raise RuntimeError("Owned browser stop failed")
            while True:
                response = await self.request("GET", f"/sessions/{session_id}")
                if not response.is_success:
                    raise RuntimeError("Owned browser status failed")
                if response.json().get("status") == "closed":
                    return
                await asyncio.sleep(0.25)

    @asynccontextmanager
    async def owned(self, options, trust=True):
        # Recover the bounded start response even when the caller cancels.
        start = asyncio.create_task(self.request("POST", "/sessions/start", json=options, timeout=60))
        cancelled = False
        try:
            response = await asyncio.shield(start)
        except asyncio.CancelledError:
            response = await start
            cancelled = True
        try:
            value = response.json()
            session_id = value.get("session_id")
        except Exception:
            raise RuntimeError("Invalid Notte start response") from None
        if not isinstance(session_id, str) or not re.fullmatch(
            r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}", session_id
        ):
            raise RuntimeError(f"Notte start returned no owned ID (HTTP {response.status_code})")
        try:
            if cancelled:
                raise asyncio.CancelledError
            if not response.is_success:
                raise RuntimeError(f"Notte start failed (HTTP {response.status_code})")
            if trust and (
                response.headers.get("X-Notte-Browser-Trust-Profile") != "evervault"
                or response.headers.get("X-Notte-Browser-Trust-SHA256") != CA_SHA256
            ):
                raise RuntimeError("Evervault browser trust was not verified")

            async def cdp():
                url = value.get("cdp_url")
                if not url:
                    debug = await self.request("GET", f"/sessions/{session_id}/debug")
                    if not debug.is_success:
                        raise RuntimeError("Notte CDP lookup failed")
                    url = debug.json().get("ws", {}).get("cdp")
                if not isinstance(url, str) or urlparse(url).scheme not in ("ws", "wss"):
                    raise RuntimeError("Invalid Notte CDP response")
                return url

            yield session_id, cdp
        finally:
            await self.close(session_id)


async def create_token(app_id, api_key, encrypted, target, transport=None):
    parsed = urlparse(target)
    if (
        not encrypted.startswith("ev:")
        or parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or "*" in parsed.hostname
    ):
        raise ValueError("Use an encrypted value and an exact HTTPS destination")
    async with httpx.AsyncClient(timeout=30, follow_redirects=False, transport=transport) as http:
        try:
            response = await http.post(
                "https://api.evervault.com/browser-tokens",
                auth=(app_id, api_key),
                json={
                    "data": [{"category": "credential.password", "value": encrypted, "id": "login-password"}],
                    "ttl": 300,
                    "permissions": [{"action": "decrypt", "target": parsed.hostname}],
                },
            )
        except Exception:
            raise RuntimeError("Evervault transport failed") from None
    if not response.is_success:
        raise RuntimeError(f"Evervault returned HTTP {response.status_code}")
    try:
        result = response.json()
        tokens = [
            item
            for item in result["data"]
            if item["id"] == "login-password" and item["category"] == "credential.password"
        ]
        proxy = result["proxyConfiguration"]
        if (
            len(tokens) != 1
            or not isinstance(tokens[0]["value"], str)
            or not tokens[0]["value"]
            or proxy["hostname"] not in ("us-va.browser.relay.evervault.app", "eu-ie.browser.relay.evervault.app")
            or type(proxy["port"]) is not int
            or not 1 <= proxy["port"] <= 65535
            or not all(isinstance(proxy[key], str) and proxy[key] for key in ("username", "password"))
            or datetime.fromisoformat(result["expiresAt"].replace("Z", "+00:00")) <= datetime.now(timezone.utc)
        ):
            raise ValueError
        return tokens[0]["value"], {
            "type": "external",
            "server": f"https://{proxy['hostname']}:{proxy['port']}",
            "username": proxy["username"],
            "password": proxy["password"],
        }
    except Exception:
        raise RuntimeError("Invalid Evervault token response") from None


async def disconnect(browser):
    try:
        await asyncio.wait_for(browser.close(), timeout=3)
    except Exception:
        raise RuntimeError("Browser disconnect failed") from None


async def fill_password(notte, proxy, token, target, connect=None):
    async with async_playwright() as playwright:
        async with notte.owned(
            {"max_duration_minutes": 3, "proxies": [proxy], "browser_trust_profile": "evervault"}
        ) as (
            session_id,
            cdp,
        ):
            browser = None
            try:
                browser = await (connect or playwright.chromium.connect_over_cdp)(await cdp(), timeout=30_000)
                page = await (browser.contexts[0] if browser.contexts else await browser.new_context()).new_page()
                await page.goto(target, wait_until="domcontentloaded", timeout=30_000)
                if urlparse(page.url)[:2] != urlparse(target)[:2]:
                    raise RuntimeError("Destination redirected outside its origin")
                await page.locator('input[name="password"]').fill(token, timeout=15_000)
                return {"session_id": session_id, "filled": True}
            except Exception:
                raise RuntimeError("Browser token form fill failed") from None
            finally:
                if browser:
                    await disconnect(browser)


async def main(tokenize=create_token):
    task = asyncio.current_task()
    loop = asyncio.get_running_loop()
    previous = signal.getsignal(signal.SIGTERM)

    def cancel(*_):
        if task:
            loop.call_soon_threadsafe(task.cancel)

    signal.signal(signal.SIGTERM, cancel)
    try:
        target = os.environ["EVERVAULT_FORM_URL"]
        token, proxy = await tokenize(
            os.environ["EVERVAULT_APP_ID"],
            os.environ["EVERVAULT_API_KEY"],
            os.environ["EVERVAULT_ENCRYPTED_PASSWORD"],
            target,
        )
        notte = Notte(os.environ["NOTTE_API_KEY"], os.environ.get("NOTTE_API_URL", "https://api.notte.cc"))
        try:
            await fill_password(notte, proxy, token, target)
            print("Token filled; owned browser closed.")
        finally:
            await notte.http.aclose()
    finally:
        signal.signal(signal.SIGTERM, previous)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (asyncio.CancelledError, KeyboardInterrupt):
        raise SystemExit("Browser Tokens task cancelled.") from None
    except Exception:
        raise SystemExit("Browser Tokens task failed.") from None
