# pyright: basic
"""Site misses and the pass/fail rules of a benchmark run (head alone, or head against base).

Rules (the workflow is red when one fails). Rules 1, 2, 5 and 6 judge the Jev runners only (`JUDGED_RUNNERS`);
the LLM and scripted runners are reported, not judged.

1. Fixture tasks (local pages, no site noise) pass in every head run.
2. Fixture probes are answered right in every head run.
3. Every planned run produced a run file.
4. Infra misses stay at or under 5% of the runs (task runs and probe answers, both versions, every runner). An
   infra miss is a run that ended on a decider transport error: the decider could not be reached, timed out or
   answered HTTP 5xx / 408. It is counted apart, not as a failure, and the harness never retries it.
5. With a base: on public sites (demo and real suites), per runner, head does not solve clearly fewer tasks than
   base. The versions are compared repeat by repeat: a site or infra miss on either side leaves that repeat out
   on both. "Clearly": the sum over tasks of
   (base success rate - head success rate) reaches `max(3, 10% of the compared tasks)`. One task flipping is not
   enough, so site noise alone does not make the run red; every task that did worse is still listed.
6. The same for public probes, per probe runner, on the rate of right answers.

Without a base, public tasks and probes are reported, not judged.
"""

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from .model import FIXTURES

# no model: they time the browser side and the CI setup
TIMING_RUNNERS = ("notte-local-scripted", "probe-local-scripted")
# the runners the rules judge (Jev); the others are reported only
JUDGED_RUNNERS = ("notte-local", "notte-local-html", "probe-local-jev")
INFRA_MISS_LIMIT = 0.05

RULES = (__doc__ or "").strip()
# pages that block automated browsers, matched in the visible text of the landing or final page
BLOCK_MARKERS = re.compile(
    r"captcha|verify you are (?:a )?human|are you a robot|unusual traffic|access denied|request blocked|"
    r"just a moment\.\.\.|attention required|client challenge|press (?:and|&) hold",
    re.IGNORECASE,
)


# a decider that could not be reached, timed out or failed on its side (`LLMProviderError` from notte_llm's Jev and
# LLM paths: "request failed: ConnectError", "failed after retries (ReadTimeout)", "returned HTTP 503", "HTTP 502 from")
TRANSPORT = re.compile(
    r"\b(?:Connect(?:Error|Timeout)|(?:Read|Write|Pool)Timeout|TimeoutException|RemoteProtocolError|NetworkError|"
    r"ReadError|WriteError)\b|\bHTTP (?:5\d\d|408)\b"
)


def infra_miss(error: str | None) -> str | None:
    """The error when it is a decider transport error (see `TRANSPORT`), else None."""
    if error and error.startswith("LLMProviderError") and TRANSPORT.search(error):
        return error[:300]
    return None


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


def probe_site_miss(url: str, run: dict[str, Any]) -> str | None:
    """Evidence that a public probe page was not there to be asked about: the same evidence as `site_miss` on its
    landing page (navigation failed, HTTP error, off the site, block page), or a recorded landing on another page
    (with `probe_landed`). The probes of such a page are site misses, not wrong answers. A run that failed without
    such evidence (the browser or session broke before a page was read) is not a site miss: its probes count wrong."""
    if url.startswith(FIXTURES):
        return None
    landing = run.get("landing")
    evidence = site_miss(url, {"nav_error": run.get("nav_error"), "landing": landing, "final": landing})
    if evidence:
        return evidence
    if run.get("probe_url") is not None and not run_landed(run, url):
        return f"landed on {run.get('probe_url')}"
    return None


@dataclass
class Row:
    """One task (or probe) and runner: head against base."""

    runner: str
    name: str
    suite: str
    fixture: bool
    # repeat -> success, for the runs that are not site or infra misses
    head_runs: dict[int, bool] = field(default_factory=dict)
    base_runs: dict[int, bool] = field(default_factory=dict)
    head_misses: list[str] = field(default_factory=list)
    base_misses: list[str] = field(default_factory=list)
    head_infra: list[str] = field(default_factory=list)
    base_infra: list[str] = field(default_factory=list)

    @property
    def head(self) -> list[bool]:
        return [self.head_runs[r] for r in sorted(self.head_runs)]

    @property
    def base(self) -> list[bool]:
        return [self.base_runs[r] for r in sorted(self.base_runs)]

    @property
    def pairs(self) -> list[tuple[bool, bool]]:
        """(base, head) of the repeats both versions ran usably: a site or infra miss on one side leaves the other
        side's run of that repeat out too."""
        return [(self.base_runs[r], self.head_runs[r]) for r in sorted(self.head_runs) if r in self.base_runs]

    @property
    def delta(self) -> float | None:
        """head - base success rate over `pairs`; None without a pair."""
        pairs = self.pairs
        if not pairs:
            return None
        return (sum(h for _, h in pairs) - sum(b for b, _ in pairs)) / len(pairs)

    def add(self, version: str | None, repeat: int, success: bool, infra: str | None, miss: str | None) -> None:
        side = "base" if version == "base" else "head"
        if infra:
            getattr(self, f"{side}_infra").append(infra)
        elif miss:
            getattr(self, f"{side}_misses").append(miss)
        else:
            getattr(self, f"{side}_runs")[repeat] = success


def task_rows(runs: list[dict[str, Any]]) -> list[Row]:
    rows: dict[tuple[str, str], Row] = {}
    for run in runs:
        key = (run["runner"], run["task"])
        row = rows.get(key)
        if row is None:
            row = rows[key] = Row(run["runner"], run["task"], run.get("suite", ""), FIXTURES in run.get("url", ""))
        row.add(
            run.get("version"),
            run["repeat"],
            bool(run.get("success")),
            infra_miss(run.get("error")),
            run.get("site_miss"),
        )
    return list(rows.values())


def probe_rows(probe_runs: list[dict[str, Any]]) -> list[Row]:
    rows: dict[tuple[str, str], Row] = {}
    for run in probe_runs:
        records = run.get("probes") or []
        if not records and run.get("error"):
            # the page or session failed before any question: every probe of the page counts as wrong, unless the
            # site (`site_miss`) or the decider (`infra_miss`) is why
            records = [{"probe": name, "correct": False, "error": run["error"]} for name in run.get("names", [])]
        for p in records:
            key = (run["runner"], p["probe"])
            row = rows.get(key)
            if row is None:
                row = rows[key] = Row(run["runner"], p["probe"], run.get("suite", ""), FIXTURES in run.get("url", ""))
            miss = run.get("site_miss") or (f"landed on {run.get('probe_url')}" if p.get("site_miss") else None)
            row.add(run.get("version"), run["repeat"], bool(p.get("correct")), infra_miss(p.get("error")), miss)
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
                pairs = r.pairs
                base, head = sum(b for b, _ in pairs), sum(h for _, h in pairs)
                verdict.warnings.append(
                    f"{runner} / {r.name}: {base}/{len(pairs)} on base, {head}/{len(pairs)} on head"
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
    rows = task_rows(runs) + probe_rows(probe_runs)
    infra = sum(len(r.head_infra) + len(r.base_infra) for r in rows)
    total = sum(len(r.head) + len(r.base) + len(r.head_misses) + len(r.base_misses) for r in rows) + infra
    if total and infra / total > INFRA_MISS_LIMIT:
        verdict.failures.append(
            f"{infra} infra misses (decider transport errors) in {total} runs: over {INFRA_MISS_LIMIT:.0%}"
        )
    runs = [r for r in runs if r["runner"] in JUDGED_RUNNERS]
    probe_runs = [r for r in probe_runs if r["runner"] in JUDGED_RUNNERS]
    for run in runs:
        failed = not run.get("success") and not infra_miss(run.get("error"))
        if run.get("version", "head") == "head" and FIXTURES in run.get("url", "") and failed:
            reason = run.get("error") or run.get("stop_reason")
            verdict.failures.append(f"fixture task {run['runner']} / {run['task']} #{run['repeat']} failed ({reason})")
    for row in probe_rows(probe_runs):
        if row.fixture and not all(row.head):
            verdict.failures.append(f"fixture probe {row.runner} / {row.name}: {sum(row.head)}/{len(row.head)} right")
    if with_base:
        _compare(task_rows(runs), "tasks solved", verdict)
        _compare(probe_rows(probe_runs), "probes answered right", verdict)
    return verdict
