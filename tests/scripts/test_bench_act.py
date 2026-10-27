"""Offline contracts of the act benchmark harness (scripts/bench_act): task registry, sharding, run order,
site misses, pass/fail rules and the merged report. No browser, no model."""

import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import Mock
from urllib.parse import urlsplit

import pytest
import yaml

from scripts.bench_act import bench, registry, report, rules
from scripts.bench_act.model import CI_CORE, CI_EXTENDED, TIERS, TODAY_ENV, Probe, Task, ci_tier, long_date, trip_dates
from scripts.bench_act.tasks.real import GF_TFS, gf_results_url, gf_search

FIXTURE_URL = "{fixtures}/form.html"


def test_discovery_works_without_installed_packages() -> None:
    subprocess.run(
        [sys.executable, "-S", "-c", "from scripts.bench_act.registry import discover; discover()"],
        cwd=Path(registry.__file__).resolve().parents[2],
        check=True,
        capture_output=True,
        text=True,
    )


def test_discover_names_every_task_and_probe_once_with_its_module_as_suite() -> None:
    found = registry.discover()
    assert len(found.tasks) == 141
    assert len(found.probes) == 161
    suites = {
        "cov_fixtures",
        "cov_real",
        "cov2_fixtures",
        "cov2_real",
        "cov3_fixtures",
        "cov3_real",
        "demo",
        "fixtures",
        "real",
    }
    assert {t.suite for t in found.tasks.values()} == suites
    assert all(t.fixture == t.suite.endswith("fixtures") for t in found.tasks.values())
    assert found.tasks["gf-book"].max_steps == 25
    assert found.tasks["search"].max_steps == 15


def test_every_fixture_url_is_a_page_in_fixtures() -> None:
    found = registry.discover()
    fixtures = Path(registry.__file__).with_name("fixtures")
    urls = [t.url for t in found.tasks.values()] + [p.url for p in found.probes.values()]
    pages = {
        urlsplit(u.replace("{fixtures}", "http://fixtures")).path.lstrip("/")
        for u in urls
        if u.startswith("{fixtures}")
    }
    assert pages and all((fixtures / page).is_file() for page in pages), sorted(
        p for p in pages if not (fixtures / p).is_file()
    )


def test_every_task_and_probe_has_one_ci_tier_and_local_pages_are_core() -> None:
    found = registry.discover()
    items = [*found.tasks.values(), *found.probes.values()]
    assert all(sum(tier in i.tags for tier in TIERS) == 1 for i in items)
    fixture_items = [i for i in items if i.fixture]
    extended = {i.name for i in fixture_items if CI_EXTENDED in i.tags}
    # a decider miss, and fixtures failing on a bug not fixed yet: see the modules' ci_tier calls
    assert extended == {
        "f-webcomp",
        "f-webcomp-speed",
        "f-drawer-open",
        "f2-vlist",
        "f2-dashboard",
        "f2-dashboard-max",
        "f2-multitab",
        "f3-wizard",
    }


def test_ci_tier_rejects_a_core_name_it_does_not_define() -> None:
    tasks = [Task("a", "https://a.test", "g", lambda f, r: True)]
    assert ci_tier(tasks, core={"a"})[0].tags == (CI_CORE,)
    with pytest.raises(ValueError, match="'b'"):
        ci_tier(tasks, core={"b"})


def test_select_by_tag_keeps_the_tasks_and_probe_pages_of_that_tier() -> None:
    reg = registry.Registry(
        {
            "t1": Task("t1", "https://a.test", "g", lambda f, r: True, tags=(CI_CORE,)),
            "t2": Task("t2", "https://b.test", "g", lambda f, r: True, tags=(CI_EXTENDED,)),
        },
        {
            "p1": Probe("p1", "https://p.test", "q?", None, "YES", tags=(CI_CORE,)),
            "p2": Probe("p2", "https://p.test", "q?", None, "NO", tags=(CI_EXTENDED,)),
        },
    )
    core = registry.select(reg, tags=[CI_CORE])
    assert [(i.kind, i.names) for i in core] == [("task", ("t1",)), ("probes", ("p1",))]
    assert len(registry.select(reg)) == 3


@pytest.mark.parametrize("tags", [["ci-extend"], [CI_CORE, "ci-extend"]])
def test_select_rejects_unknown_tags_even_alongside_known_tags(tags: list[str]) -> None:
    with pytest.raises(ValueError, match="unknown tag 'ci-extend'"):
        registry.select(registry.discover(), tags=tags)


def test_select_accepts_probe_only_tags_and_allows_empty_shards() -> None:
    reg = registry.Registry({}, {"p": Probe("p", "https://p.test", "q?", None, "YES", tags=("probe-tag",))})
    items = registry.select(reg, tags=["probe-tag"])
    assert [item.names for item in items] == [("p",)]
    assert registry.shard(items, 2, 2) == []


def test_discover_rejects_a_name_defined_in_two_modules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = tmp_path / "duplicated_tasks"
    package.mkdir()
    (package / "__init__.py").write_text("")
    entry = "from scripts.bench_act.model import Task\nTASKS = [Task('same', 'https://a.test', 'goal', lambda f, r: True)]\n"
    (package / "a.py").write_text(entry)
    (package / "b.py").write_text(entry)
    monkeypatch.syspath_prepend(str(tmp_path))
    import duplicated_tasks  # pyright: ignore[reportMissingImports]

    with pytest.raises(ValueError, match="'same' is defined twice"):
        registry.discover(duplicated_tasks)
    sys.modules.pop("duplicated_tasks", None)


def _registry() -> registry.Registry:
    def ok(_: dict[str, Any], __: dict[str, Any]) -> bool:
        return True

    tasks = [Task(f"f{i}", "{fixtures}/x.html", "g", ok, suite="fixtures") for i in range(4)]
    tasks += [Task(f"r{i}", "https://r.test", "g", ok, suite="real") for i in range(7)]
    probes = [
        Probe("p1", "https://p.test/a", "q?", None, "YES", suite="real"),
        Probe("p2", "https://p.test/b", "q?", None, "NO", suite="real"),
        Probe("p3", "https://p.test/a", "q?", ["x", "y"], "x", suite="real"),
        Probe("p4", FIXTURE_URL, "q?", None, "NO", suite="fixtures"),
    ]
    return registry.Registry({t.name: t for t in tasks}, {p.name: p for p in probes})


def test_select_groups_probes_by_page_and_filters_by_suite_and_name() -> None:
    reg = _registry()
    items = registry.select(reg)
    assert [i.key for i in items if i.kind == "task"] == [f"f{i}" for i in range(4)] + [f"r{i}" for i in range(7)]
    pages = {i.key: i.names for i in items if i.kind == "probes"}
    assert pages == {"https://p.test/a": ("p1", "p3"), "https://p.test/b": ("p2",), FIXTURE_URL: ("p4",)}
    assert {i.key for i in registry.select(reg, suites=["fixtures"])} == {"f0", "f1", "f2", "f3", FIXTURE_URL}
    assert [i.key for i in registry.select(reg, tasks=["r3"], with_probes=False)] == ["r3"]
    assert [i.names for i in registry.select(reg, probes=["p3"], with_tasks=False)] == [("p3",)]
    with pytest.raises(ValueError, match="unknown task"):
        registry.select(reg, tasks=["nope"])


@pytest.mark.parametrize("count", [1, 2, 3, 4, 7])
def test_shards_split_every_item_once_and_spread_each_suite(count: int) -> None:
    items = registry.select(registry.discover())
    shards = [registry.shard(items, i, count) for i in range(1, count + 1)]
    assert sorted((i.kind, i.key) for s in shards for i in s) == sorted((i.kind, i.key) for i in items)
    assert shards == [registry.shard(items, i, count) for i in range(1, count + 1)]
    for suite in (
        "fixtures",
        "demo",
        "real",
        "cov_fixtures",
        "cov_real",
        "cov2_fixtures",
        "cov2_real",
        "cov3_fixtures",
        "cov3_real",
    ):
        sizes = [sum(i.suite == suite and i.kind == "task" for i in s) for s in shards]
        assert max(sizes) - min(sizes) <= 1


@pytest.mark.parametrize("spec", ["0/2", "3/2", "x/2", "1"])
def test_parse_shard_rejects_bad_specs(spec: str) -> None:
    with pytest.raises(ValueError):
        registry.parse_shard(spec)


def test_plan_runs_versions_back_to_back_alternating_and_longest_first() -> None:
    items = registry.select(_registry())
    jobs = registry.plan(items, ["notte-local", "probe-local-jev"], ["base", "head"], repeats=2)
    # every item runs on its kind of runner only, once per version and repeat
    assert {(j.item.kind, j.runner) for j in jobs} == {("task", "notte-local"), ("probes", "probe-local-jev")}
    assert len(jobs) == len(items) * 2 * 2
    pairs = [jobs[k : k + 2] for k in range(0, len(jobs), 2)]
    assert all(
        a.item == b.item and a.runner == b.runner and {a.version, b.version} == {"base", "head"} for a, b in pairs
    )
    firsts = [a.version for a, _ in pairs]
    assert firsts[: len(items)] == ["base", "head"] * (len(items) // 2) + ["base"] * (len(items) % 2)
    # repeat 2 starts each item with the other version
    assert firsts[len(items) :] == ["head" if v == "base" else "base" for v in firsts[: len(items)]]
    # public tasks first, then probe pages, then fixture tasks
    order = [("fixture" if j.item.fixture and j.item.kind == "task" else j.item.kind) for j, _ in pairs[: len(items)]]
    assert order == ["task"] * 7 + ["probes"] * 3 + ["fixture"] * 4
    assert jobs[0].file == "base/notte-local__r0__1.json"


def test_site_miss_needs_evidence_from_the_site() -> None:
    url = "https://www.example.com/start"
    assert rules.site_miss(url, {"success": True, "nav_error": "x"}) == "navigation failed: x"
    assert rules.site_miss("{fixtures}/a.html", {"success": True, "nav_error": "x"}) is None
    assert rules.site_miss("{fixtures}/a.html", {"success": False, "nav_error": "x"}) is None
    assert rules.site_miss(url, {"success": False}) is None
    assert rules.site_miss(url, {"nav_error": "TimeoutError: goto"}) == "navigation failed: TimeoutError: goto"
    assert rules.site_miss(url, {"landing": {"url": url, "status": 403}}) == f"HTTP 403 on {url}"
    assert rules.site_miss(url, {"landing": {"url": "https://consent.example.com/x", "status": 200}}) is None
    assert rules.site_miss(url, {"landing": {"url": "https://other.test/", "status": 200}}) == (
        "redirected to https://other.test/"
    )
    final = {"url": "https://www.example.com/search", "text": "Enter the characters seen in the image below: CAPTCHA"}
    assert rules.site_miss(url, {"landing": {"url": url, "status": 200}, "final": final}) == (
        "block page ('CAPTCHA') on https://www.example.com/search"
    )


@pytest.mark.parametrize("stage", ["landing", "final"])
@pytest.mark.parametrize("problem", ["block", "redirect"])
def test_task_success_does_not_override_block_or_redirect_evidence(stage: str, problem: str) -> None:
    task = registry.discover().tasks["pypi"]
    expected_url = "https://pypi.org/project/requests/2.31.0/"
    landing = {"url": expected_url, "status": 200, "text": "requests 2.31.0"}
    final = {"url": expected_url, "text": "requests 2.31.0"}
    page = landing if stage == "landing" else final
    if problem == "block":
        page["text"] = "Verify you are human"
    else:
        page["url"] = "https://other.test/project/requests/2.31.0/"
    # The real path-only checker accepts this result, including the wrong final host.
    assert task.check(final, {}) is True
    run = {"runner": "notte-local", "task": task.name, "suite": "real", "version": "head",
           "repeat": 1, "success": True, "landing": landing, "final": final}  # fmt: skip
    miss = rules.site_miss(task.url, run)
    assert miss is not None
    assert ("block page" if problem == "block" else "redirected to") in miss
    run["site_miss"] = miss
    [row] = rules.task_rows([run])
    assert row.head == []
    assert row.head_misses == [miss]


def test_probe_landed_keeps_host_and_query() -> None:
    intended = "https://www.booking.com/searchresults.html?ss=Lisbon&checkin=2026-11-13"
    assert rules.probe_landed(intended, intended + "&lang=en")
    assert rules.probe_landed(intended, "https://www.booking.com/searchresults.html?ss=Lisbon;checkin=2026-11-13")
    assert not rules.probe_landed(intended, "https://www.booking.com/index.html")
    assert not rules.probe_landed(intended, None)


def _task_run(task: str, version: str, success: bool, **extra: Any) -> dict[str, Any]:
    url = "{fixtures}/x.html" if task.startswith("f") else f"https://{task}.test/"
    suite = "fixtures" if task.startswith("f") else "real"
    return {"runner": "notte-local", "task": task, "url": url, "suite": suite, "version": version, "repeat": 1,
            "success": success, "stop_reason": "done", **extra}  # fmt: skip


def _public(base: list[bool], head: list[bool], **head_extra: Any) -> list[dict[str, Any]]:
    runs = [_task_run(f"r{i}", "base", ok) for i, ok in enumerate(base)]
    return runs + [_task_run(f"r{i}", "head", ok, **head_extra) for i, ok in enumerate(head)]


def test_a_failed_fixture_task_or_probe_or_a_missing_run_fails() -> None:
    assert rules.judge([_task_run("f1", "head", True)], [], [], with_base=False).ok
    verdict = rules.judge([_task_run("f1", "head", False), _task_run("f2", "base", False)], [], [], with_base=False)
    assert verdict.failures == ["fixture task notte-local / f1 #1 failed (done)"]
    probes = [{"runner": "probe-local-jev", "url": FIXTURE_URL, "suite": "fixtures", "version": "head", "repeat": 1,
               "probes": [{"probe": "p4", "correct": False}]}]  # fmt: skip
    assert rules.judge([], probes, [], with_base=False).failures == ["fixture probe probe-local-jev / p4: 0/1 right"]
    assert rules.judge([], [], ["head/x.json"], with_base=False).failures == ["no run file: head/x.json"]


def test_public_sites_fail_only_on_a_clear_drop_against_base() -> None:
    twenty = [True] * 20
    # two flips: listed, not failing
    verdict = rules.judge(_public(twenty, [False, False] + [True] * 18), [], [], with_base=True)
    assert verdict.ok
    assert len(verdict.warnings) == 2
    # three flips over 20 compared tasks reach max(3, 10%)
    verdict = rules.judge(_public(twenty, [False] * 3 + [True] * 17), [], [], with_base=True)
    assert verdict.failures == ["notte-local: 3 fewer tasks solved than base over 20 public ones (limit 3)"]
    # improvements offset drops
    assert rules.judge(_public([False] + [True] * 19, [True] + [False] * 3 + [True] * 16), [], [], with_base=True).ok
    # without a base, public sites are only reported
    assert rules.judge([r for r in _public(twenty, [False] * 20) if r["version"] == "head"], [], [], False).ok


def test_site_misses_are_left_out_of_the_comparison() -> None:
    runs = _public([True] * 20, [False] * 20, site_miss="HTTP 403 on https://r.test/")
    verdict = rules.judge(runs, [], [], with_base=True)
    assert verdict.ok and not verdict.warnings
    rows = rules.task_rows(runs)
    assert all(r.delta is None and r.head_misses for r in rows)


def test_public_probes_compare_rates_of_right_answers() -> None:
    def run(version: str, correct: list[bool]) -> dict[str, Any]:
        return {"runner": "probe-local-jev", "url": "https://p.test", "suite": "real", "version": version,
                "repeat": 1, "probes": [{"probe": f"p{i}", "correct": c} for i, c in enumerate(correct)]}  # fmt: skip

    assert rules.judge([], [run("base", [True] * 10), run("head", [False] * 2 + [True] * 8)], [], True).ok
    verdict = rules.judge([], [run("base", [True] * 10), run("head", [False] * 3 + [True] * 7)], [], True)
    assert verdict.failures == [
        "probe-local-jev: 3 fewer probes answered right than base over 10 public ones (limit 3)"
    ]


def _write(directory: Path, name: str, record: dict[str, Any]) -> None:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record))


def test_report_merges_shard_directories_and_writes_the_summary(tmp_path: Path) -> None:
    shards = [tmp_path / "shard-1", tmp_path / "shard-2"]
    plans = [["base/notte-local__f1__1.json", "head/notte-local__f1__1.json"], ["head/notte-local__r1__1.json"]]
    for directory, jobs, n in zip(shards, plans, (1, 2), strict=True):
        meta = {"shard": f"{n}/2", "concurrency": 2, "runners": ["notte-local"], "suites": [], "repeats": 1,
                "trees": {"base": "a" * 40, "head": "b" * 40}, "jobs": jobs}  # fmt: skip
        _write(directory, f"_meta/plan-shard-{n}-of-2.json", meta)
        _write(directory, f"_meta/timing-shard-{n}-of-2.json", {**meta, "wall_s": 90, "cpu_count": 4,
               "load_max": 3.1, "load_mean": 2.0, "runs": [{"file": jobs[0], "seconds": 40}]})  # fmt: skip
    _write(shards[0], "base/notte-local__f1__1.json", _task_run("f1", "base", True))
    _write(shards[0], "head/notte-local__f1__1.json", _task_run("f1", "head", True))
    runs, probe_runs, meta = report.load(shards)
    assert len(runs) == 2 and not probe_runs and len(meta) == 4
    missing = report.missing_runs(shards, meta)
    assert missing == ["head/notte-local__r1__1.json"]
    verdict = rules.judge(runs, probe_runs, missing, with_base=True)
    text = report.ci_summary(runs, probe_runs, meta, verdict)
    assert text.startswith("## act bench: FAIL")
    assert "- no run file: head/notte-local__r1__1.json" in text
    assert "base `aaaaaaaaaa` · head `bbbbbbbbbb`" in text
    assert "| notte-local | fixtures | 1/1 | 1/1 | 0 |" in text
    assert "| 2/2 | 1 | 2 | 1.5 min | 40 s (head/notte-local__r1__1.json) | 3.1 / 2.0 (4) |" in text
    assert "| notte-local | head | 1 | – | – |" in text


def test_report_check_exits_non_zero_when_a_rule_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(tmp_path, "head/notte-local__f1__1.json", _task_run("f1", "head", False))
    summary = tmp_path / "summary.md"
    monkeypatch.setattr(sys, "argv", ["report.py", str(tmp_path), "--summary", str(summary), "--check"])
    with pytest.raises(SystemExit) as exit_info:
        report.main()
    assert exit_info.value.code == 1
    assert "fixture task notte-local / f1 #1 failed" in summary.read_text()


def test_report_uses_only_planned_runs_but_still_fails_for_missing_results(tmp_path: Path) -> None:
    task = "head/notte-local__f-core__1.json"
    probe = "head/probe-local-jev__core__1.json"
    _write(tmp_path, task, _task_run("f-core", "head", True))
    _write(tmp_path, "head/notte-local__f-extended__1.json", _task_run("f-extended", "head", False))
    for name, correct in (("core", True), ("extended", False)):
        _write(
            tmp_path,
            f"head/probe-local-jev__{name}__1.json",
            {
                "runner": "probe-local-jev",
                "url": FIXTURE_URL,
                "suite": "fixtures",
                "version": "head",
                "repeat": 1,
                "probes": [{"probe": name, "correct": correct}],
            },
        )
    # The previous all-tier run fails on extended fixtures.
    runs, probes, meta = report.load([tmp_path])
    assert not rules.judge(runs, probes, [], with_base=False).ok
    _write(tmp_path, "_meta/plan-shard-1-of-1.json", {"jobs": [task, probe]})
    runs, probes, meta = report.load([tmp_path])
    assert [r["task"] for r in runs] == ["f-core"]
    assert [p["probe"] for r in probes for p in r["probes"]] == ["core"]
    assert rules.judge(runs, probes, report.missing_runs([tmp_path], meta), with_base=False).ok
    (tmp_path / probe).unlink()
    runs, probes, meta = report.load([tmp_path])
    verdict = rules.judge(runs, probes, report.missing_runs([tmp_path], meta), with_base=False)
    assert verdict.failures == [f"no run file: {probe}"]


def test_gf_search_decodes_google_flights_urls_for_any_trip_date() -> None:
    captured = gf_results_url(date(2026, 11, 13))
    assert captured.split("tfs=")[1].split("&")[0] == GF_TFS
    search = gf_search(gf_results_url(date(2027, 2, 5)))
    assert search is not None
    assert search["trip"] == 2
    [leg] = search["legs"]
    assert leg["date"] == "2027-02-05" and "/m/05qtj" in leg["from"] and "/m/07dfk" in leg["to"]
    assert gf_search("https://www.google.com/travel/flights") is None


def test_scripted_decider_scrolls_then_is_done_without_a_model() -> None:
    import asyncio

    from notte_core.act import DecisionState, PageState, Question

    from scripts.bench_act.runners import ScriptedDecider

    decider = ScriptedDecider()
    state = DecisionState(page=PageState(url="https://a.test", title="a", text=""))
    questions = {
        "operation": Question(criteria={"CLICK": "click", "SCROLL_DOWN": "scroll", "DONE": "done"}),
        "click_target": Question(criteria={"I1": "a button", "I2": "a link"}),
    }
    ops = [asyncio.run(decider.choose(state, questions)).answers["operation"].choice for _ in range(4)]
    assert ops == ["SCROLL_DOWN", "SCROLL_DOWN", "DONE", "DONE"]
    answers = asyncio.run(decider.choose(state, questions))
    assert answers.model == "scripted" and answers.answers["click_target"].choice == "I1"


def test_scripted_runners_are_never_judged() -> None:
    run = {**_task_run("f1", "head", False), "runner": "notte-local-scripted"}
    assert rules.judge([run], [], [], with_base=False).ok


def test_landing_is_read_after_a_redirect_on_load_and_never_fails_the_run() -> None:
    import asyncio

    from scripts.bench_act.runners import _landing  # pyright: ignore[reportPrivateUsage]

    class Page:
        url = "https://www.example.com/landed"

        def __init__(self, failures: int) -> None:
            self.failures = failures
            self.waited = False

        async def evaluate(self, _: str) -> str:
            if self.failures:
                self.failures -= 1
                raise RuntimeError("Execution context was destroyed, most likely because of a navigation")
            return json.dumps({"url": self.url, "status": 200, "text": "ok"})

        async def wait_for_load_state(self, state: str, timeout: float) -> None:
            self.waited = True

    page = Page(failures=1)
    assert asyncio.run(_landing(page)) == {"url": page.url, "status": 200, "text": "ok"}
    assert page.waited
    landing = asyncio.run(_landing(Page(failures=2)))
    assert landing["url"] == Page.url and landing["status"] is None and "Execution context" in landing["error"]


JEV_CONNECT = (
    "LLMProviderError: Jev via the OpenRouter decisions endpoint (https://openrouter.ai/api/alpha/decisions) "
    "request failed: ConnectError; no action executed."
)


@pytest.mark.parametrize(
    ("error", "infra"),
    [
        (JEV_CONNECT, True),
        ("LLMProviderError: Jev via the OpenRouter decisions endpoint (...) returned HTTP 503: busy; no action", True),
        ("LLMProviderError: LLM request to google/gemini-3.1-flash-lite failed after retries (ReadTimeout)", True),
        ("LLMProviderError: HTTP 502 from LLM model google/gemini-3.1-flash-lite: bad gateway", True),
        ("LLMProviderError: Jev via the OpenRouter decisions endpoint (...) returned HTTP 400: bad request", False),
        ("RateLimitError: Rate limit exceeded for provider openrouter", False),
        ("Error: net::ERR_CONNECTION_REFUSED ConnectError at https://site.test", False),
        ("timeout: no result after 900 s", False),
        (None, False),
    ],
)
def test_infra_misses_are_decider_transport_errors_only(error: str | None, infra: bool) -> None:
    assert (rules.infra_miss(error) is not None) == infra


def test_llm_runners_are_reported_not_judged() -> None:
    llm = [{**_task_run("f1", "head", False), "runner": "notte-local-llm"}]
    llm += [{**r, "runner": "notte-local-llm"} for r in _public([True] * 20, [False] * 20)]
    probes = [{"runner": "probe-local-llm", "url": FIXTURE_URL, "suite": "fixtures", "version": "head", "repeat": 1,
               "probes": [{"probe": "p4", "correct": False}]}]  # fmt: skip
    verdict = rules.judge(llm, probes, [], with_base=True)
    assert verdict.ok and not verdict.warnings


def test_an_infra_miss_is_counted_apart_and_fails_only_above_five_percent() -> None:
    # 1 infra miss in 20 runs (5%): the fixture run is not a failure, and the public pair is left out
    runs = [_task_run("f1", "head", False, error=JEV_CONNECT)] + [
        _task_run(f"f{i}", "head", True) for i in range(2, 20)
    ]
    runs.append(_task_run("r0", "head", True))
    verdict = rules.judge(runs, [], [], with_base=False)
    assert verdict.ok
    [row] = [r for r in rules.task_rows(runs) if r.name == "f1"]
    assert row.head == [] and row.head_infra == [JEV_CONNECT]
    # 2 in 20 (10%) fail the run
    runs[1] = _task_run("f2", "head", False, error=JEV_CONNECT)
    assert rules.judge(runs, [], [], with_base=False).failures == [
        "2 infra misses (decider transport errors) in 20 runs: over 5%"
    ]
    # an infra miss on head is not a drop against base
    public = _public([True] * 20, [True] * 19 + [False])
    public[-1]["error"] = JEV_CONNECT
    rows = rules.task_rows(public)
    assert [r.delta for r in rows if r.head_infra] == [None]


def test_summary_shows_infra_misses_and_report_only_runners() -> None:
    runs = [
        _task_run("r1", "head", False, error=JEV_CONNECT),
        {**_task_run("r2", "head", True), "runner": "notte-local-llm"},
    ]
    text = report.ci_summary(runs, [], [], rules.judge(runs, [], [], with_base=False))
    assert "| runner | suite | head | site misses | infra misses |" in text
    assert "| notte-local | real | 0/0 | 0 | 1 |" in text
    assert "| notte-local-llm (report only) | real | 1/1 | 0 | 0 |" in text
    assert "0/0 (+1 infra miss)" in text


def test_trip_dates_are_a_friday_four_to_five_weeks_ahead(monkeypatch: pytest.MonkeyPatch) -> None:
    trip = trip_dates(date(2026, 10, 26))
    assert trip.depart == date(2026, 11, 27) and trip.depart.weekday() == 4
    assert (trip.back, trip.checkout) == (date(2026, 12, 4), date(2026, 11, 29))
    assert trip_dates(date(2026, 10, 30)).depart == date(2026, 11, 27)  # 28 days ahead is already a Friday
    monkeypatch.setenv(TODAY_ENV, "2027-03-01")
    assert trip_dates().depart == date(2027, 4, 2)
    assert long_date(date(2026, 11, 27)) == "27 November 2026"


def test_probe_pages_that_are_not_there_are_site_misses() -> None:
    url = "https://books.test/a"
    ok = {"landing": {"url": url, "status": 200, "text": "A book"}, "probe_url": url}
    assert rules.probe_site_miss(url, ok) is None
    assert rules.probe_site_miss(url, {"nav_error": "TimeoutError: goto"}) == "navigation failed: TimeoutError: goto"
    assert rules.probe_site_miss(url, {**ok, "landing": {"url": url, "status": 429, "text": ""}}) == (
        f"HTTP 429 on {url}"
    )
    captcha = {**ok, "landing": {"url": url, "status": 200, "text": "Please solve this CAPTCHA"}}
    assert rules.probe_site_miss(url, captcha) == f"block page ('CAPTCHA') on {url}"
    assert rules.probe_site_miss(url, {**ok, "probe_url": "https://consent.test/"}) == "landed on https://consent.test/"
    assert rules.probe_site_miss(FIXTURE_URL, {"nav_error": "x"}) is None
    # the browser broke before any page was read: no site evidence, so the probes count wrong
    crashed = {"error": "BrowserError: launch failed"}
    assert rules.probe_site_miss(url, crashed) is None
    page = {"runner": "probe-local-jev", "url": url, "suite": "real", "version": "head", "repeat": 1, "names": ["p1"],
            **crashed, "site_miss": None}  # fmt: skip
    [row] = rules.probe_rows([page])
    assert (row.head, row.head_misses) == ([False], [])
    # a page that failed before any question: its probes are site misses, not wrong answers
    run = {"runner": "probe-local-jev", "url": url, "suite": "real", "version": "head", "repeat": 1,
           "names": ["p1", "p2"], "error": "TimeoutError: goto", "site_miss": "navigation failed: TimeoutError: goto"}  # fmt: skip
    [r1, r2] = rules.probe_rows([run])
    assert (r1.head, r1.head_misses, r2.head) == ([], ["navigation failed: TimeoutError: goto"], [])


def test_versions_are_compared_repeat_by_repeat() -> None:
    def run(version: str, repeat: int, success: bool, miss: str | None = None) -> dict[str, Any]:
        return {**_task_run("r1", version, success), "repeat": repeat, "site_miss": miss}

    # base pass, pass, fail; head pass, site miss, fail: the usable pairs agree
    runs = [run("base", 1, True), run("base", 2, True), run("base", 3, False)]
    runs += [run("head", 1, True), run("head", 2, False, "HTTP 503 on x"), run("head", 3, False)]
    [row] = rules.task_rows(runs)
    assert row.pairs == [(True, True), (False, False)] and row.delta == 0
    assert row.base == [True, True, False] and row.head == [True, False]
    assert not rules.judge(runs, [], [], with_base=True).warnings


def test_unknown_suites_are_rejected() -> None:
    with pytest.raises(ValueError, match="unknown suite 'fixture'"):
        registry.select(_registry(), suites=["fixture"])


def test_upload_is_a_blocked_capability_check() -> None:
    [upload] = [t for t in registry.discover().tasks.values() if t.name == "upload"]
    final = {"url": "https://the-internet.herokuapp.com/upload", "text": "File Uploader"}
    blocked = {"steps": [{"status": "blocked", "operation": "BLOCKED"}]}
    typed = {"steps": [{"status": "executed", "operation": "TYPE_TEXT"}, {"status": "blocked"}]}
    assert upload.check(final, blocked)
    assert not upload.check(final, typed)


def test_resume_keeps_only_runs_of_the_same_commit_and_identity(tmp_path: Path) -> None:
    path = tmp_path / "run.json"
    path.write_text(json.dumps({"sha": "a" * 40}))
    assert not bench.kept(path, "a" * 40, "inputs")
    path.write_text(json.dumps({"sha": "a" * 40, "run_identity": "inputs"}))
    assert bench.kept(path, "a" * 40, "inputs")
    assert not bench.kept(path, "a" * 40, "changed")
    assert not bench.kept(path, "b" * 40, "inputs")
    assert not bench.kept(path, None, "inputs")


@pytest.mark.parametrize("contents", ["{", "[]", "null", '"not a run"'])
def test_resume_does_not_keep_corrupt_or_non_object_runs(tmp_path: Path, contents: str) -> None:
    path = tmp_path / "run.json"
    assert not bench.kept(path, "a" * 40, "inputs")
    path.write_text(contents)
    assert not bench.kept(path, "a" * 40, "inputs")


@pytest.mark.parametrize("contents", ["{", "[]", "null"])
def test_invalid_worker_output_is_a_failed_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, contents: str) -> None:
    harness = tmp_path / "harness"
    harness.mkdir()
    monkeypatch.setattr(bench, "HARNESS", harness)
    process = Mock(returncode=1)
    start = Mock(return_value=process)
    monkeypatch.setattr(bench.subprocess, "Popen", start)

    def finish(timeout: float) -> int:
        command = start.call_args.args[0]
        Path(command[command.index("--out") + 1]).write_text(contents)
        return 1

    process.wait.side_effect = finish
    found = registry.discover()
    [item] = registry.select(found, tasks=["search"], with_probes=False)
    job = registry.Job("head", "notte-local", item, 1)
    result = bench.run_job(
        job,
        {"head": tmp_path},
        {"head": "a" * 40},
        {"search": found.tasks["search"].url},
        "http://127.0.0.1:1000",
        tmp_path / "out",
        900,
        "2026-10-26",
    )
    record = json.loads((tmp_path / "out" / job.file).read_text())
    assert result["returncode"] == 1
    assert record["success"] is False and record["stop_reason"] == "error"
    assert record["site_miss"] is None and record["error"]
    assert record["run_identity"]


@pytest.mark.parametrize("consent", [None, "accepted", "rejected", "unknown"])
def test_cookie_task_requires_consent_to_be_handled(consent: str | None) -> None:
    task = registry.discover().tasks["cookie"]
    assert task.check({"url": "http://fixture.test/pricing.html", "consent": consent}, {}) == (
        consent in {"accepted", "rejected"}
    )


def test_run_job_reruns_changed_probe_selection_and_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    harness = tmp_path / "harness"
    harness.mkdir()
    worker = harness / "worker.py"
    worker.write_text("# harness version 1")
    monkeypatch.setattr(bench, "HARNESS", harness)
    process = Mock(returncode=0)
    start = Mock(return_value=process)
    monkeypatch.setattr(bench.subprocess, "Popen", start)

    def finish(timeout: float) -> int:
        command = start.call_args.args[0]
        spec = json.loads(command[command.index("--job") + 1])
        path = Path(command[command.index("--out") + 1])
        path.write_text(json.dumps({**spec, "probes": [{"probe": n, "correct": True} for n in spec["names"]]}))
        return 0

    process.wait.side_effect = finish
    found = registry.discover()
    core = next(i for i in registry.select(found, tags=[CI_CORE]) if "price" in i.names)
    all_tiers = next(i for i in registry.select(found) if "price" in i.names)
    assert "star-rating" not in core.names and "star-rating" in all_tiers.names

    def run(item: registry.Item, today: str = "2026-10-26", timeout: float = 900, port: int = 1000) -> bool:
        result = bench.run_job(
            registry.Job("head", "probe-local-jev", item, 1),
            {"head": tmp_path},
            {"head": "a" * 40},
            {},
            f"http://127.0.0.1:{port}",
            tmp_path / "out",
            timeout,
            today,
        )
        return result.get("skipped", False)

    assert not run(core)
    assert run(core, port=2000)  # a restarted fixture server is still the same fixture input
    assert not run(all_tiers)
    assert start.call_count == 2
    [path] = (tmp_path / "out/head").glob("*.json")
    assert "star-rating" in [p["probe"] for p in json.loads(path.read_text())["probes"]]
    assert run(all_tiers)
    assert not run(all_tiers, today="2026-10-27")
    assert not run(all_tiers, today="2026-10-27", timeout=30)
    worker.write_text("# harness version 2")
    assert not run(all_tiers, today="2026-10-27", timeout=30)
    assert start.call_count == 5


@pytest.mark.parametrize("action", ["opened", "synchronize", "reopened", "labeled"])
@pytest.mark.parametrize("label", ["act-bench", "act-bench-all", "unrelated"])
def test_benchmark_labels_share_push_concurrency_group(action: str, label: str) -> None:
    workflow = yaml.safe_load((Path(__file__).resolve().parents[2] / ".github/workflows/act-bench.yml").read_text())
    assert action in workflow[True]["pull_request"]["types"]  # YAML 1.1 parses `on` as True
    context = {
        "github.event.pull_request.number": 1324,
        "github.run_id": 5678,
        "github.event.action": action,
        "github.event.label.name": label,
    }

    def evaluate(match: re.Match[str]) -> str:
        expression = re.sub(r"github[\w.]+", lambda token: repr(context[token.group()]), match[1])
        expression = expression.replace("&&", " and ").replace("||", " or ")
        return str(eval(expression, {"__builtins__": {}}))

    group = re.sub(r"\$\{\{(.*?)\}\}", evaluate, workflow["concurrency"]["group"])
    suffix = "5678" if action == "labeled" and label == "unrelated" else "bench"
    assert group == f"act-bench-1324-{suffix}"
    assert workflow["concurrency"]["cancel-in-progress"] is True


def test_trees_are_base_and_head_only(tmp_path: Path) -> None:
    assert bench.parse_trees([], tmp_path) == {"head": tmp_path}
    trees = bench.parse_trees([f"head={tmp_path}/h", f"base={tmp_path}/b"], tmp_path)
    assert list(trees) == ["base", "head"]
    for specs in ([f"main={tmp_path}"], [f"base={tmp_path}"], [f"head={tmp_path}", f"head={tmp_path}"], ["head="]):
        with pytest.raises(ValueError):
            bench.parse_trees(specs, tmp_path)


def test_each_version_pair_is_one_sequential_group() -> None:
    items = registry.select(_registry())
    jobs = registry.plan(items, ["notte-local", "probe-local-jev"], ["base", "head"], repeats=2)
    groups = registry.pairs(jobs)
    assert [job for group in groups for job in group] == jobs
    assert all(len(g) == 2 and len({(j.runner, j.item, j.repeat) for j in g}) == 1 for g in groups)
