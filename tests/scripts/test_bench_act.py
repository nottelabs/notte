"""Offline contracts of the act benchmark harness (scripts/bench_act): task registry, sharding, run order,
site misses, pass/fail rules and the merged report. No browser, no model."""

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.bench_act import registry, report, rules
from scripts.bench_act.model import Probe, Task
from scripts.bench_act.tasks.real import GF_RESULTS, gf_search

FIXTURE_URL = "{fixtures}/form.html"


def test_discover_names_every_task_and_probe_once_with_its_module_as_suite() -> None:
    found = registry.discover()
    assert len(found.tasks) == 37
    assert len(found.probes) == 47
    assert {t.suite for t in found.tasks.values()} == {"demo", "fixtures", "real"}
    assert all(t.fixture == (t.suite == "fixtures") for t in found.tasks.values())
    assert found.tasks["gf-book"].max_steps == 25
    assert found.tasks["search"].max_steps == 15


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
    for suite in ("fixtures", "demo", "real"):
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
    assert rules.site_miss(url, {"success": True, "nav_error": "x"}) is None
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


def test_gf_search_decodes_google_flights_urls() -> None:
    search = gf_search(GF_RESULTS)
    assert search is not None
    assert search["trip"] == 2
    [leg] = search["legs"]
    assert leg["date"] == "2026-11-13" and "/m/05qtj" in leg["from"] and "/m/07dfk" in leg["to"]
    assert gf_search("https://www.google.com/travel/flights") is None
