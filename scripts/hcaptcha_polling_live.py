"""Opt-in hCaptcha polling checks on NopeCHA, using backend CAPTCHA_API_KEY.

Run with --api-url URL --scenario resume|navigate|close|concurrent --output FILE.
The demo checks token delivery/callbacks, not server-side token acceptance.
"""

import argparse
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from loguru import logger
from notte_sdk.client import NotteClient


def run(args):
    logger.remove()
    wire = []
    pending = threading.Event()
    action_pending = threading.Event()

    def client():
        c = NotteClient(api_key=os.environ["NOTTE_API_KEY"], server_url=args.api_url, captcha_timeout_seconds=240)
        request = c.sessions.page.request

        def record(endpoint, **kwargs):
            start = time.monotonic()
            r = request(endpoint, **kwargs)
            wire.append(
                {
                    "seconds": time.monotonic() - start,
                    "action": r.action.type,
                    **r.model_dump(mode="json", include={"success", "code", "action_executed", "captcha"}),
                }
            )
            if r.captcha and r.captcha.state == "solving":
                pending.set()
                if r.action.type == "evaluate_js" and r.action_executed is False:
                    action_pending.set()
            return r

        c.sessions.page.request = record
        return c

    def outcome(future):
        try:
            r = future.result(timeout=5)
            return r.model_dump(mode="json", include={"success", "code", "action_executed", "captcha"})
        except Exception as exc:
            return {"error_type": type(exc).__name__, "http_status": getattr(exc, "status_code", None)}

    c = client()
    row = {"scenario": args.scenario, "wire": wire, "provider": "anti-captcha", "started_at": time.time()}
    with c.Session(headless=True, proxies=False, solve_captchas=False, idle_timeout_minutes=3) as s:
        row["session_id"] = s.session_id
        print(json.dumps({"session_id": s.session_id, "scenario": args.scenario}), flush=True)
        p = s.page
        p.goto("https://nopecha.com/captcha/hcaptcha", wait_until="domcontentloaded", timeout=45000)
        p.locator('iframe[src*="hcaptcha.com"]').first.wait_for(timeout=30000)
        p.evaluate("window.__hcaptchaProbe = 0")
        other = client().Session(session_id=s.session_id)
        with ThreadPoolExecutor(max_workers=2) as pool:
            solve = pool.submit(s.execute, type="captcha_solve", captcha_type="hcaptcha", raise_on_failure=False)
            deadline = time.monotonic() + 250
            while not pending.is_set() and not solve.done() and time.monotonic() < deadline:
                p.wait_for_timeout(100)
            row["observed_pending"] = pending.is_set()
            if args.scenario == "concurrent":
                action = pool.submit(
                    other.execute, type="captcha_solve", captcha_type="hcaptcha", raise_on_failure=False
                )
            else:
                action = pool.submit(
                    other.execute,
                    type="evaluate_js",
                    code="window.__hcaptchaProbe += 1; document.title",
                    raise_on_failure=False,
                )
                while not action_pending.is_set() and not action.done() and time.monotonic() < deadline:
                    p.wait_for_timeout(100)
                row["observed_blocked_action"] = action_pending.is_set()
                row["executions_while_pending"] = p.evaluate("window.__hcaptchaProbe")
            if args.scenario == "navigate" and action_pending.is_set():
                p.goto("https://example.com", wait_until="domcontentloaded")
            elif args.scenario == "close" and action_pending.is_set():
                client().sessions.stop(s.session_id)
            while (not solve.done() or not action.done()) and time.monotonic() < deadline:
                if args.scenario == "close":
                    time.sleep(0.1)
                else:
                    p.wait_for_timeout(100)
            row["solve_result"] = outcome(solve)
            row["action_result"] = outcome(action)
        if args.scenario in ("resume", "concurrent"):
            row["executions_final"] = p.evaluate("window.__hcaptchaProbe")
            row["callback_success"] = p.locator(".response").inner_text().strip() == "success"
            row["response_present"] = p.locator('[name="h-captcha-response"]').evaluate_all(
                "els => els.some(e => Boolean(e.value.trim()))"
            )
    row["finished_at"] = time.time()
    row["assessment"] = assess(row)
    return row


def assess(row):
    if not row["observed_pending"]:
        return "inconclusive: no pending solve observed"
    if row["scenario"] != "concurrent" and not row["observed_blocked_action"]:
        return "inconclusive: no blocked action observed"
    if row["scenario"] in ("navigate", "close"):

        def cancelled(result):
            return result.get("code") in ("captcha_cancelled", "captcha_page_changed") or (
                row["scenario"] == "close" and result.get("http_status") in (404, 410)
            )

        actions = [r for r in row["wire"] if r["action"] == "evaluate_js"]
        passed = (
            row["executions_while_pending"] == 0
            and len(actions) == 1
            and cancelled(row["solve_result"])
            and cancelled(row["action_result"])
        )
    else:
        passed = all(row[k].get("success") for k in ("solve_result", "action_result"))
        passed = passed and row["callback_success"] and row["response_present"]
        if row["scenario"] == "resume":
            passed = passed and row["executions_while_pending"] == 0 and row["executions_final"] == 1
        else:
            passed = passed and len({r["captcha"]["captcha_id"] for r in row["wire"] if r.get("captcha")}) == 1
    return "passed" if passed else "failed"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--scenario", choices=["resume", "navigate", "close", "concurrent"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        row = run(args)
    except Exception as exc:
        row = {"assessment": "failed", "error_type": type(exc).__name__}
    args.output.write_text(json.dumps(row, indent=2))
    print(json.dumps(row), flush=True)
    raise SystemExit(0 if row["assessment"] == "passed" else 2 if row["assessment"].startswith("inconclusive") else 1)
