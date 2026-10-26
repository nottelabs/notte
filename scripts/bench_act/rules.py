# pyright: basic
"""Site misses and the pass/fail rules of a benchmark run (head alone, or head against base).

Rules (the workflow is red when one fails):

1. Fixture tasks (local pages, no site noise) pass in every head run, for every runner.
2. Fixture probes are answered right in every head run.
3. Every planned run produced a run file.
4. With a base: on public sites (demo and real suites), per runner, head does not solve clearly fewer tasks than
   base. Runs that are site misses on either side are left out. "Clearly": the sum over tasks of
   (base success rate - head success rate) reaches `max(3, 10% of the compared tasks)`. One task flipping is not
   enough, so site noise alone does not make the run red; every task that did worse is still listed.
5. The same for public probes, per probe runner, on the rate of right answers.

Without a base, public tasks and probes are reported, not judged. The scripted runners (no model, timing only)
are never judged.
"""

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from .model import FIXTURES

# no model: they time the browser side and the CI setup, and are not judged
TIMING_RUNNERS = ("notte-local-scripted", "probe-local-scripted")

RULES = (__doc__ or "").strip()
# pages that block automated browsers, matched in the visible text of the landing or final page
BLOCK_MARKERS = re.compile(
    r"captcha|verify you are (?:a )?human|are you a robot|unusual traffic|access denied|request blocked|"
    r"just a moment\.\.\.|attention required|client challenge|press (?:and|&) hold",
    re.IGNORECASE,
)


def stop_reason(run: dict[str, Any], max_steps: int) -> str:
    """Why the loop ended: the last status (done / blocked / stale), an error, the unchanged-page guard, or
    the step cap."""
    steps = run.get("steps") or []
    if run.get("error"):
        return "error"
    if not steps:
        return "no-step"
    last = steps[-1].get("status")
    if last in ("done", "blocked", "stale"):
        return last
    if len(steps) >= max_steps:
        return "max-steps"
    return "unchanged-guard"


def registrable_domain(url: str) -> str:
    host = urlsplit(url).hostname or ""
    return ".".join(host.split(".")[-2:])


def site_miss(url: str, run: dict[str, Any]) -> str | None:
    """Evidence that the site, not act or observe, made a failed public-site run fail; None when there is none:
    the first navigation failed, answered an HTTP error, or left the site, or the landing or final page is a block
    page (CAPTCHA, bot check)."""
    if run.get("success") or url.startswith(FIXTURES):
        return None
    if run.get("nav_error"):
        return f"navigation failed: {run['nav_error'][:200]}"
    landing = run.get("landing") or {}
    status = landing.get("status")
    if isinstance(status, int) and status >= 400:
        return f"HTTP {status} on {landing.get('url')}"
    if landing.get("url") and registrable_domain(landing["url"]) != registrable_domain(url):
        return f"redirected to {landing['url']}"
    for page in (landing, run.get("final") or {}):
        match = BLOCK_MARKERS.search(page.get("text") or "")
        if match:
            return f"block page ({match.group(0)!r}) on {page.get('url')}"
    return None


def _query(url: str) -> dict[str, str]:
    # booking.com separates its own parameters with ";"
    return dict(parse_qsl(urlsplit(url).query.replace(";", "&"), keep_blank_values=True))


def probe_landed(intended: str, landed: str | None) -> bool:
    """Whether a probe page is the one its questions are about: the same host, with every query parameter of the
    intended URL kept. A site that redirects elsewhere (booking.com's results page to a bare URL without the
    search) is a site miss, not a wrong answer."""
    if landed is None:
        return False
    if urlsplit(intended).hostname != urlsplit(landed).hostname:
        return False
    kept = _query(landed)
    return all(kept.get(key) == value for key, value in _query(intended).items())


def run_landed(run: dict[str, Any], url: str) -> bool:
    """`probe_landed` on the URL read before the questions and, when recorded, after them."""
    urls = [run.get("probe_url")] + ([run["probe_url_end"]] if "probe_url_end" in run else [])
    return all(probe_landed(url, u) for u in urls)


@dataclass
class Row:
    """One task (or probe) and runner: head against base."""

    runner: str
    name: str
    suite: str
    fixture: bool
    head: list[bool] = field(default_factory=list)
    base: list[bool] = field(default_factory=list)
    head_misses: list[str] = field(default_factory=list)
    base_misses: list[str] = field(default_factory=list)

    @staticmethod
    def _rate(values: list[bool]) -> float | None:
        return sum(values) / len(values) if values else None

    @property
    def head_rate(self) -> float | None:
        return self._rate(self.head)

    @property
    def base_rate(self) -> float | None:
        return self._rate(self.base)

    @property
    def delta(self) -> float | None:
        """head - base success rate, over the runs that are not site misses; None if either side has none."""
        if self.head_rate is None or self.base_rate is None:
            return None
        return self.head_rate - self.base_rate


def task_rows(runs: list[dict[str, Any]]) -> list[Row]:
    rows: dict[tuple[str, str], Row] = {}
    for run in runs:
        key = (run["runner"], run["task"])
        row = rows.get(key)
        if row is None:
            row = rows[key] = Row(run["runner"], run["task"], run.get("suite", ""), FIXTURES in run.get("url", ""))
        miss = run.get("site_miss")
        side = "base" if run.get("version") == "base" else "head"
        if miss:
            getattr(row, f"{side}_misses").append(miss)
        else:
            getattr(row, side).append(bool(run.get("success")))
    return list(rows.values())


def probe_rows(probe_runs: list[dict[str, Any]]) -> list[Row]:
    rows: dict[tuple[str, str], Row] = {}
    for run in probe_runs:
        side = "base" if run.get("version") == "base" else "head"
        records = run.get("probes") or []
        if not records and run.get("error"):
            # the page or session failed before any question: every probe of the page counts as wrong
            records = [{"probe": name, "correct": False} for name in run.get("names", [])]
        for p in records:
            key = (run["runner"], p["probe"])
            row = rows.get(key)
            if row is None:
                row = rows[key] = Row(run["runner"], p["probe"], run.get("suite", ""), FIXTURES in run.get("url", ""))
            if p.get("site_miss"):
                getattr(row, f"{side}_misses").append(f"landed on {run.get('probe_url')}")
            else:
                getattr(row, side).append(bool(p.get("correct")))
    return list(rows.values())


def threshold(compared: int) -> int:
    return max(3, math.ceil(0.1 * compared))


@dataclass
class Verdict:
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures


def _compare(rows: list[Row], what: str, verdict: Verdict) -> None:
    by_runner: dict[str, list[Row]] = defaultdict(list)
    for row in rows:
        if not row.fixture:
            by_runner[row.runner].append(row)
    for runner, runner_rows in by_runner.items():
        compared = [r for r in runner_rows if r.delta is not None]
        if not compared:
            continue
        drop = -sum(r.delta for r in compared if r.delta is not None)
        limit = threshold(len(compared))
        for r in sorted(compared, key=lambda r: r.delta or 0):
            if r.delta is not None and r.delta < 0:
                verdict.warnings.append(
                    f"{runner} / {r.name}: {sum(r.base)}/{len(r.base)} on base, {sum(r.head)}/{len(r.head)} on head"
                )
        if drop >= limit:
            verdict.failures.append(
                f"{runner}: {drop:g} fewer {what} than base over {len(compared)} public ones (limit {limit})"
            )


def judge(runs: list[dict[str, Any]], probe_runs: list[dict[str, Any]], missing: list[str], with_base: bool) -> Verdict:
    verdict = Verdict()
    runs = [r for r in runs if r["runner"] not in TIMING_RUNNERS]
    probe_runs = [r for r in probe_runs if r["runner"] not in TIMING_RUNNERS]
    for path in missing:
        verdict.failures.append(f"no run file: {path}")
    for run in runs:
        if run.get("version", "head") == "head" and FIXTURES in run.get("url", "") and not run.get("success"):
            reason = run.get("error") or run.get("stop_reason")
            verdict.failures.append(f"fixture task {run['runner']} / {run['task']} #{run['repeat']} failed ({reason})")
    for row in probe_rows(probe_runs):
        if row.fixture and not all(row.head):
            verdict.failures.append(f"fixture probe {row.runner} / {row.name}: {sum(row.head)}/{len(row.head)} right")
    if with_base:
        _compare(task_rows(runs), "tasks solved", verdict)
        _compare(probe_rows(probe_runs), "probes answered right", verdict)
    return verdict
