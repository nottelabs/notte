"""Opt-in functional checks against 2Captcha demos using an updated SDK.

Example: python scripts/captcha_polling_live.py --api-url https://preview-7-dev-test.notte.cc \
  --kind recaptcha --scenario auto --runs 3 --output /tmp/captcha-auto.json
Credentials come from NOTTE_API_KEY. This creates real sessions/provider work.
"""

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from loguru import logger
from notte_sdk.client import NotteClient

DEMOS = {
    "recaptcha": "https://2captcha.com/demo/recaptcha-v2",
    "turnstile": "https://2captcha.com/demo/cloudflare-turnstile",
}
CHECK = 'button[data-action="demo_action"]'


def run(args):
    logger.remove()
    wire = []
    pending = threading.Event()
    client = NotteClient(api_key=os.environ["NOTTE_API_KEY"], server_url=args.api_url, captcha_timeout_seconds=180)
    request = client.sessions.page.request

    def record(endpoint, *, _request=request, **kwargs):
        start = time.monotonic()
        try:
            result = _request(endpoint, **kwargs)
        except Exception as exc:
            wire.append(
                {
                    "at": time.time(),
                    "seconds": time.monotonic() - start,
                    "error_type": type(exc).__name__,
                    "http_status": getattr(exc, "status_code", None),
                }
            )
            raise
        wire.append(
            {
                "at": time.time(),
                "seconds": time.monotonic() - start,
                **result.model_dump(mode="json", include={"success", "code", "action_executed", "captcha"}),
                "action": result.action.type,
            }
        )
        if result.captcha and result.captcha.state == "solving":
            pending.set()
        return result

    client.sessions.page.request = record
    row = {"kind": args.kind, "scenario": args.scenario, "started_at": time.time(), "wire": wire}
    with client.Session(
        headless=True,
        browser_type="chromium",
        proxies=False,
        solve_captchas=args.scenario != "explicit",
        idle_timeout_minutes=3,
    ) as session:
        row["session_id"] = session.session_id
        page = session.page
        page.add_init_script("""window.__captchaClicks=0;
          document.addEventListener('click', e => {
            if(e.target.closest('button[data-action="demo_action"]')) window.__captchaClicks++;
          },true);""")
        page.goto(DEMOS[args.kind], wait_until="domcontentloaded")
        page.locator(CHECK).wait_for(timeout=30000)
        if args.kind == "recaptcha":
            page.frame_locator('iframe[src*="/recaptcha/api2/anchor"]').locator("#recaptcha-anchor").wait_for(
                timeout=30000
            )
        page.wait_for_timeout(2500)
        row["before_action_at"] = time.time()
        row["frames_before_action"] = [f.url.split("?")[0] for f in page.frames]
        action = (
            {"type": "captcha_solve"}
            if args.scenario in ("explicit", "concurrent")
            else {"type": "click", "selector": CHECK}
        )
        with ThreadPoolExecutor(max_workers=2) as pool:
            future = pool.submit(session.execute, **action, raise_on_failure=False)
            second = None
            if args.scenario == "concurrent":
                other = NotteClient(
                    api_key=os.environ["NOTTE_API_KEY"], server_url=args.api_url, captcha_timeout_seconds=180
                )
                other_request = other.sessions.page.request
                other.sessions.page.request = lambda endpoint, **kwargs: record(
                    endpoint, _request=other_request, **kwargs
                )
                other_session = other.Session(session_id=session.session_id)
                second = pool.submit(other_session.execute, type="captcha_solve", raise_on_failure=False)
            deadline = time.monotonic() + 190
            while not future.done() and not pending.is_set() and time.monotonic() < deadline:
                page.wait_for_timeout(100)
            row["observed_pending"] = pending.is_set()
            row["clicks_while_pending"] = page.evaluate("window.__captchaClicks")
            if pending.is_set() and args.scenario == "navigate":
                page.goto("https://example.com", wait_until="domcontentloaded")
            elif pending.is_set() and args.scenario == "close":
                # Separate HTTP caller closes the actual backend session.
                other = NotteClient(api_key=os.environ["NOTTE_API_KEY"], server_url=args.api_url)
                other.sessions.stop(session.session_id)
            while not future.done() and time.monotonic() < deadline:
                if args.scenario == "close":
                    time.sleep(0.1)
                else:
                    page.wait_for_timeout(100)
            try:
                result = future.result(timeout=5)
                row["result"] = result.model_dump(
                    mode="json", include={"success", "code", "action_executed", "captcha", "message"}
                )
            except Exception as exc:
                row["error_type"] = type(exc).__name__
                row["http_status"] = getattr(exc, "status_code", None)
            if second:
                try:
                    row["second_success"] = second.result(timeout=5).success
                except Exception as exc:
                    row["second_error_type"] = type(exc).__name__
        if args.scenario not in ("close", "navigate"):
            if args.scenario in ("explicit", "concurrent") and row.get("result", {}).get("success"):
                row["verification_action_success"] = session.execute(
                    type="click", selector=CHECK, raise_on_failure=False
                ).success
            page.wait_for_timeout(2500)
            row["clicks_final"] = page.evaluate("window.__captchaClicks")
            row["form_text"] = page.locator("form").first.inner_text()[:1000]
            row["verification_passed"] = "Captcha is passed successfully!" in row["form_text"]
        row["finished_at"] = time.time()
    row["assessment"] = assess(row)
    return row


def assess(row):
    pending_responses = [r for r in row["wire"] if (r.get("captcha") or {}).get("state") == "solving"]
    if row["scenario"] in ("navigate", "close"):
        if not row.get("observed_pending") or row.get("clicks_while_pending") != 0:
            return "inconclusive: no blocked action observed"
        result = row.get("result", {})
        terminal = result.get("code") in ("captcha_cancelled", "captcha_page_changed")
        closed = row["scenario"] == "close" and row.get("http_status") in (404, 410)
        clicks = [r for r in row["wire"] if r.get("action") == "click"]
        return "passed" if (terminal or closed) and len(clicks) == 1 else "failed"
    if not row.get("result", {}).get("success") or not row.get("verification_passed"):
        return "failed"
    if row.get("clicks_final") != 1:
        return "failed"
    if not pending_responses:
        return "inconclusive: solve completed before polling was observed"
    if row["scenario"] == "auto" and row.get("clicks_while_pending") != 0:
        return "inconclusive: action executed before a CAPTCHA wait"
    if row["scenario"] == "concurrent":
        solve_ids = {r["captcha"]["captcha_id"] for r in row["wire"] if r.get("captcha")}
        if not row.get("second_success") or len(solve_ids) != 1:
            return "failed"
    return "passed"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--kind", choices=DEMOS, required=True)
    parser.add_argument("--scenario", choices=["auto", "explicit", "navigate", "close", "concurrent"], required=True)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")
    results = []
    for attempt in range(args.runs):
        if attempt:
            time.sleep(5)
        try:
            row = run(args)
        except Exception as exc:
            row = {"kind": args.kind, "scenario": args.scenario, "error_type": type(exc).__name__}
        results.append(row)
        args.output.write_text(json.dumps(results, indent=2))
        print(json.dumps(row), flush=True)
    sys.exit(1 if any(r.get("assessment", "failed") == "failed" for r in results) else 0)
