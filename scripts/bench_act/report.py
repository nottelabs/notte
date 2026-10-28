# pyright: basic
"""Merge the run files of `bench.py` (one or several output directories, e.g. one per CI shard) into Markdown.

uv run --no-sync python scripts/bench_act/report.py DIR [DIR ...] [--tasks a,b] [--runners x,y] [--failures]
# CI: base against head, the pass/fail rules of `rules.py`; exit 1 when they fail
python scripts/bench_act/report.py runs --summary summary.md --check
"""

import sys
from pathlib import Path

if not __package__:  # run as a script: import the harness as the `bench_act` package
    sys.path[0] = str(Path(__file__).resolve().parents[1])
    __package__ = "bench_act"

import argparse  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import statistics  # noqa: E402
from collections import defaultdict  # noqa: E402
from typing import Any  # noqa: E402

from .records import matches_plan, read_record  # noqa: E402
from .rules import JUDGED_RUNNERS, RULES, Row, Verdict, judge, probe_rows, task_rows  # noqa: E402

STEP_TIMINGS = ("observe", "decide", "write", "fresh", "execute")


def _p(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    values = sorted(values)
    return values[min(len(values) - 1, int(round(q * (len(values) - 1))))]


def _mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else float("nan")


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def _rate(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return f"{k}/{n} ({100 * k / n:.0f}%, {100 * lo:.0f}–{100 * hi:.0f})" if n else "–"


def load(directories: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """(task runs, probe runs, shard metadata), from the run files under each directory."""
    runs, probes, meta = [], [], []
    paths = [(directory, path) for directory in directories for path in sorted(directory.rglob("*.json"))]
    for _, path in paths:
        if "_meta" in path.parts:
            meta.append({**json.loads(path.read_text()), "file": path.name})
    plans = [m for m in meta if m["file"].startswith("plan-")]
    planned = {job for m in plans for job in m["jobs"]}
    expected = {job: m["expected"][job] for m in plans for job in m["jobs"]}
    for directory, path in paths:
        relative = str(path.relative_to(directory))
        if "_meta" in path.parts or (plans and relative not in planned):
            continue
        data = json.loads(path.read_text()) if not plans else read_record(path)
        if plans and not matches_plan(data, expected[relative]):
            continue
        assert isinstance(data, dict)
        data["file"] = relative
        data.setdefault("version", "head")
        runner = data["runner"]
        assert isinstance(runner, str)
        (probes if runner.startswith("probe-") else runs).append(data)
    return runs, probes, meta


def missing_runs(directories: list[Path], meta: list[dict[str, Any]]) -> list[str]:
    """Planned runs with no complete, matching result in any shard directory."""
    expected = {job: m["expected"][job] for m in meta if m["file"].startswith("plan-") for job in m["jobs"]}
    return sorted(
        job for job, spec in expected.items() if not any(matches_plan(read_record(d / job), spec) for d in directories)
    )


def _decides(step: dict[str, Any]) -> list[dict[str, Any]]:
    return step.get("decide", [])


# OpenRouter list prices ($ per token), for calls it reports at cost 0 (gemini-3.1-flash-lite in this bench)
LIST_PRICES = {"google/gemini-3.1-flash-lite": (0.25e-6, 1.5e-6)}


def call_cost(call: dict[str, Any]) -> float:
    if call.get("cost"):
        return float(call["cost"])
    price = LIST_PRICES.get(str(call.get("model")))
    if price is None:
        return 0.0
    return (call.get("input_tokens") or 0) * price[0] + (call.get("output_tokens") or 0) * price[1]


def _cost(run: dict[str, Any]) -> tuple[float, float]:
    decide = sum(call_cost(j) for s in run.get("steps", []) for j in _decides(s))
    writer = sum(call_cost(w) for s in run.get("steps", []) for w in s.get("writer", []))
    return decide, writer


def summary(runs: list[dict[str, Any]]) -> dict[str, Any]:
    steps = [s for r in runs for s in r.get("steps", [])]
    decisions = [j for s in steps for j in _decides(s)]
    timed = [s for s in steps if s.get("status") != "error"]
    costs = [_cost(r) for r in runs]
    walls = [r["wall_ms"] / 1000 for r in runs if r.get("wall_ms") is not None]
    writes = [w for s in steps for w in s.get("writer", [])]
    confidences = [s["confidence"] for s in steps if s.get("confidence") is not None and s.get("status") == "executed"]
    return {
        "runs": len(runs),
        "success": sum(bool(r.get("success")) for r in runs),
        "steps": _mean([len(r.get("steps", [])) for r in runs]),
        "actions": _mean([sum(s.get("status") == "executed" for s in r.get("steps", [])) for r in runs]),
        "tokens": _mean([j["input_tokens"] for j in decisions if j.get("input_tokens")]),
        "out_tokens": _mean([j["output_tokens"] for j in decisions if j.get("output_tokens")]),
        "cost": _mean([a + b for a, b in costs]),
        "decide_cost_total": sum(a for a, _ in costs),
        "writer_cost_total": sum(b for _, b in costs),
        "p50_step": _p([s["timings"]["step_ms"] for s in timed], 0.5),
        "p90_step": _p([s["timings"]["step_ms"] for s in timed], 0.9),
        "wall": _mean(walls),
        "stale": sum(1 for s in steps if s.get("stale_retry")),
        "stale_results": sum(1 for s in steps if s.get("status") == "stale"),
        "errors": sum(1 for r in runs if r.get("error")),
        "exec_failures": sum(1 for s in steps if s.get("execution_success") is False),
        "confidence": _mean(confidences),
        "writes": len(writes),
        "writer_call_p50": _p([w["ms"] for w in writes], 0.5),
        "writer_call_p90": _p([w["ms"] for w in writes], 0.9),
        "fallbacks": sum(1 for w in writes if not str(w.get("model", "")).startswith("inception/")),
        "write_errors": sum(1 for w in writes if w.get("error")),
        **{f"{k}_p50": _p([s["timings"].get(f"{k}_ms", 0) for s in timed], 0.5) for k in STEP_TIMINGS},
        **{f"{k}_p90": _p([s["timings"].get(f"{k}_ms", 0) for s in timed], 0.9) for k in STEP_TIMINGS},
        **{f"{k}_mean": _mean([s["timings"].get(f"{k}_ms", 0) for s in timed]) for k in STEP_TIMINGS},
    }


def table(groups: dict[str, list[dict[str, Any]]]) -> str:
    lines = [
        "| runner | success (95% CI) | mean steps (actions) | decide in tokens/step | cost/task | p50 / p90 step | wall/task | stale re-decisions (stale results) | failed executions | errors | mean conf (exec) |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, runs in groups.items():
        s = summary(runs)
        lines.append(
            f"| {name} | {_rate(s['success'], s['runs'])} | {s['steps']:.1f} ({s['actions']:.1f}) | {s['tokens']:.0f} | "
            f"${s['cost']:.5f} | {s['p50_step'] / 1000:.2f} / {s['p90_step'] / 1000:.2f} s | {s['wall']:.1f} s | "
            f"{s['stale']} ({s['stale_results']}) | {s['exec_failures']} | {s['errors']} | {s['confidence']:.2f} |"
        )
    return "\n".join(lines)


def timing_table(groups: dict[str, list[dict[str, Any]]]) -> str:
    lines = [
        "| runner | " + " | ".join(STEP_TIMINGS) + " | step p50 / p90 |",
        "|---|" + "---|" * (len(STEP_TIMINGS) + 1),
    ]
    for name, runs in groups.items():
        s = summary(runs)
        lines.append(
            f"| {name} | "
            + " | ".join(f"{s[k + '_mean']:.0f} ({s[k + '_p50']:.0f} / {s[k + '_p90']:.0f})" for k in STEP_TIMINGS)
            + f" | {s['p50_step']:.0f} / {s['p90_step']:.0f} |"
        )
    return "\n".join(lines)


def matrix(groups: dict[str, list[dict[str, Any]]], tasks: list[str]) -> str:
    cells: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for name, runs in groups.items():
        for r in runs:
            cells[(name, r["task"])].append(bool(r.get("success")))
    lines = ["| task | " + " | ".join(groups) + " |", "|---|" + "---|" * len(groups)]
    for task in tasks:
        row = []
        for name in groups:
            values = cells.get((name, task))
            row.append("–" if not values else f"{sum(values)}/{len(values)}")
        lines.append(f"| {task} | " + " | ".join(row) + " |")
    totals = []
    for name in groups:
        values = [v for (g, _), vs in cells.items() if g == name for v in vs]
        totals.append(f"**{sum(values)}/{len(values)}**")
    lines.append("| all | " + " | ".join(totals) + " |")
    return "\n".join(lines)


def _step_line(s: dict[str, Any]) -> str:
    status = s.get("status")
    if status == "error":
        return f"ERROR {s.get('error', '')[:140]}"
    op = s.get("operation") or "?"
    label = s.get("target_label")
    text = s.get("text")
    conf = s.get("confidence")
    part = op + (f" {label!r}" if label else "") + (f" ← {text!r}" if text else "")
    part += f" ({conf:.2f})" if isinstance(conf, (int, float)) else ""
    if status != "executed":
        part += f" [{status}]"
    if s.get("execution_success") is False:
        part += " [exec failed: " + (s.get("message") or "")[:90].replace("\n", " ") + "]"
    if s.get("stale_retry"):
        part += " [re-decided]"
    return part


def failures(runs: list[dict[str, Any]]) -> str:
    lines = []
    for r in runs:
        if r.get("success"):
            continue
        final = (r.get("final") or {}).get("url")
        lines.append(
            f"- **{r['version']} / {r['runner']} / {r['task']} #{r['repeat']}** → final `{final}`"
            + (f", error `{r['error'][:150]}`" if r.get("error") else "")
            + (f", site miss: {r['site_miss']}" if r.get("site_miss") else "")
        )
        lines.append("  " + " → ".join(_step_line(s) for s in r.get("steps", [])))
    return "\n".join(lines)


def stop_reasons(groups: dict[str, list[dict[str, Any]]]) -> str:
    """Why each run ended, per runner (success / failure)."""
    reasons = sorted({r.get("stop_reason", "?") for rs in groups.values() for r in rs})
    lines = ["| runner | " + " | ".join(reasons) + " |", "|---|" + "---|" * len(reasons)]
    for name, runs in groups.items():
        cells = []
        for reason in reasons:
            rs = [r for r in runs if r.get("stop_reason", "?") == reason]
            cells.append(f"{len(rs)} ({sum(bool(r.get('success')) for r in rs)} ok)" if rs else "–")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def confidence_vs_outcome(groups: dict[str, list[dict[str, Any]]]) -> str:
    """Does the lowest confidence of a run's executed steps predict its failure?"""
    lines = [
        "| runner | mean min conf, successful runs | failed runs | runs with min conf < 0.5: success | ≥ 0.5: success | AUC (min conf → success) |",
        "|---|---|---|---|---|---|",
    ]
    for name, runs in groups.items():
        pairs = []
        for r in runs:
            confs = [
                s["confidence"]
                for s in r.get("steps", [])
                if s.get("status") in ("executed", "done") and s.get("confidence") is not None
            ]
            if confs:
                pairs.append((min(confs), bool(r.get("success"))))
        ok = [c for c, w in pairs if w]
        bad = [c for c, w in pairs if not w]
        low = [w for c, w in pairs if c < 0.5]
        high = [w for c, w in pairs if c >= 0.5]
        auc = _mean([1.0 if a > b else 0.5 if a == b else 0.0 for a in ok for b in bad]) if ok and bad else float("nan")
        lines.append(
            f"| {name} | {_mean(ok):.2f} | {_mean(bad):.2f} | {sum(low)}/{len(low)} | {sum(high)}/{len(high)} | {auc:.2f} |"
        )
    return "\n".join(lines)


# --------------------------------------------------------------------------- probes


def probe_records(probe_runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for run in probe_runs:
        group = f"{run['version']}/{run['runner']}"
        for p in run.get("probes", []):
            out.append({**p, "runner": group, "repeat": run["repeat"]})
        if run.get("error") and not run.get("probes"):
            out.append({"runner": group, "probe": run["file"], "error": run["error"], "correct": False})
    return out


def _confidence(p: dict[str, Any]) -> float | None:
    """The probability the decider put on its own answer."""
    if p.get("kind") == "choose" and p.get("probabilities"):
        return max(p["probabilities"].values())
    if p.get("kind") == "check" and p.get("p_yes") is not None:
        return max(p["p_yes"], 1 - p["p_yes"])
    return None


def probe_tables(records: list[dict[str, Any]]) -> str:
    """Scored on the probes that landed on their page; site misses are counted apart."""
    runners = list(dict.fromkeys(r["runner"] for r in records))
    missed = [r for r in records if r.get("site_miss")]
    records = [r for r in records if not r.get("site_miss")]
    lines = [
        "| runner | choose accuracy | check accuracy | all | site miss (not scored) | mean p(right answer) | Brier (check) | mean confidence when right / wrong | p50 latency |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for runner in runners:
        rs = [r for r in records if r["runner"] == runner]
        choose = [r for r in rs if r.get("kind") == "choose"]
        check = [r for r in rs if r.get("kind") == "check"]
        brier = _mean(
            [(r["p_yes"] - (1.0 if r["answer"] == "YES" else 0.0)) ** 2 for r in check if r.get("p_yes") is not None]
        )
        right = [c for r in rs if r["correct"] and (c := _confidence(r)) is not None]
        wrong = [c for r in rs if not r["correct"] and (c := _confidence(r)) is not None]
        lines.append(
            f"| {runner} | {_rate(sum(r['correct'] for r in choose), len(choose))} | "
            f"{_rate(sum(r['correct'] for r in check), len(check))} | {_rate(sum(r['correct'] for r in rs), len(rs))} | "
            f"{sum(r['runner'] == runner for r in missed)} | "
            f"{_mean([r['p_answer'] for r in rs if r.get('p_answer') is not None]):.3f} | {brier:.3f} | "
            f"{_mean(right):.2f} / {_mean(wrong):.2f} | {_p([r['ms'] for r in rs if 'ms' in r], 0.5):.0f} ms |"
        )
    # calibration: confidence bins vs accuracy (all probe runners with probabilities)
    lines += ["", "| runner | confidence bin | n | accuracy |", "|---|---|---|---|"]
    for runner in runners:
        rs = [(c, r["correct"]) for r in records if r["runner"] == runner and (c := _confidence(r)) is not None]
        for lo, hi in ((0.0, 0.6), (0.6, 0.8), (0.8, 0.95), (0.95, 1.01)):
            b = [ok for c, ok in rs if lo <= c < hi]
            if b:
                lines.append(
                    f"| {runner} | [{lo:.2f}, {min(hi, 1.0):.2f}{']' if hi > 1 else ')'} | {len(b)} | {sum(b)}/{len(b)} |"
                )
    # per probe
    probes = list(dict.fromkeys(r["probe"] for r in records + missed))
    lines += ["", "| probe | kind | answer | " + " | ".join(runners) + " |", "|---|---|---|" + "---|" * len(runners)]
    for name in probes:
        rs = [r for r in records if r["probe"] == name]
        first = next(r for r in records + missed if r["probe"] == name)
        cells = []
        for runner in runners:
            mine = [r for r in rs if r["runner"] == runner]
            misses = sum(r["probe"] == name and r["runner"] == runner for r in missed)
            if not mine:
                cells.append(f"site miss ×{misses}" if misses else "–")
                continue
            ps = [r.get("p_answer") for r in mine]
            got = [
                r.get("choice") if r.get("kind") == "choose" else ("YES" if (r.get("p_yes") or 0) >= 0.5 else "NO")
                for r in mine
            ]
            cells.append(
                f"{sum(r['correct'] for r in mine)}/{len(mine)} p={'/'.join('err' if p is None else f'{p:.2f}' for p in ps)}"
                + ("" if all(r["correct"] for r in mine) else f" (got {', '.join(map(str, got))})")
                + (f" + site miss ×{misses}" if misses else "")
            )
        lines.append(f"| {name} | {first.get('kind')} | {first.get('answer')} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def probe_cost(records: list[dict[str, Any]]) -> dict[str, float]:
    costs: dict[str, float] = defaultdict(float)
    for r in records:
        costs[r["runner"]] += sum(call_cost(d) for d in r.get("decide", []))
    return dict(costs)


def tables(runs: list[dict[str, Any]], probe_runs: list[dict[str, Any]], show_failures: bool) -> str:
    """The detailed tables, per version and runner."""
    out: list[str] = []
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in sorted(runs, key=lambda r: (r["runner"], r["version"])):
        groups[f"{r['version']}/{r['runner']}"].append(r)
    total_decide = total_writer = 0.0
    if runs:
        out += [table(groups), timing_table(groups), matrix(groups, list(dict.fromkeys(r["task"] for r in runs)))]
        out += [confidence_vs_outcome(groups), stop_reasons(groups)]
        costs = []
        for name, rs in groups.items():
            s = summary(rs)
            total_decide += s["decide_cost_total"]
            total_writer += s["writer_cost_total"]
            costs.append(
                f"{name}: writes={s['writes']} write p50/p90={s['writer_call_p50']:.0f}/{s['writer_call_p90']:.0f} ms "
                f"fallbacks={s['fallbacks']} write_errors={s['write_errors']} decide_cost={s['decide_cost_total']:.4f} "
                f"writer_cost={s['writer_cost_total']:.4f} out_tokens={s['out_tokens']:.0f}"
            )
        out.append("\n".join(costs))
    records = probe_records(probe_runs)
    if records:
        out.append(probe_tables(records))
        pc = probe_cost(records)
        out.append("probe cost: " + ", ".join(f"{k} ${v:.5f}" for k, v in pc.items()))
        total_decide += sum(pc.values())
    out.append(
        f"TOTAL model cost: decide ${total_decide:.4f} + writer ${total_writer:.4f} = ${total_decide + total_writer:.4f}"
    )
    if show_failures:
        out.append(failures(runs))
    return "\n\n".join(out)


# --------------------------------------------------------------------------- base against head (CI summary)


def _cell(values: list[bool], misses: list[str], infra: list[str]) -> str:
    if not values and not misses and not infra:
        return "–"
    return (
        f"{sum(values)}/{len(values)}"
        + (f" (+{len(misses)} site miss)" if misses else "")
        + (f" (+{len(infra)} infra miss)" if infra else "")
    )


def _cells(row: Row, versions: list[str]) -> list[str]:
    return [
        _cell(row.base, row.base_misses, row.base_infra)
        if v == "base"
        else _cell(row.head, row.head_misses, row.head_infra)
        for v in versions
    ]


def _runner_label(runner: str) -> str:
    return runner if runner in JUDGED_RUNNERS else f"{runner} (report only)"


def _row_note(row: Row) -> str:
    notes = []
    if row.delta is not None and row.delta < 0:
        notes.append("**worse**")
    elif row.delta is not None and row.delta > 0:
        notes.append("better")
    if row.fixture and not all(row.head) and row.runner in JUDGED_RUNNERS:
        notes.append("**fixture failed**")
    for miss in dict.fromkeys(row.head_misses + row.base_misses):
        notes.append(f"site miss: {miss[:120]}")
    for infra in dict.fromkeys(row.head_infra + row.base_infra):
        notes.append(f"infra miss: {infra[:120]}")
    return "; ".join(notes).replace("|", "\\|")


def _suite_table(rows: list[Row], versions: list[str]) -> list[str]:
    lines = [
        "| runner | suite | " + " | ".join(versions) + " | site misses | infra misses |",
        "|---|---|" + "---|" * (len(versions) + 2),
    ]
    groups: dict[tuple[str, str], list[Row]] = defaultdict(list)
    for row in rows:
        groups[(row.runner, row.suite)].append(row)
    for (runner, suite), rs in sorted(groups.items()):
        cells = []
        for version in versions:
            values = [v for r in rs for v in (r.base if version == "base" else r.head)]
            cells.append(f"{sum(values)}/{len(values)}")
        misses = sum(len(r.head_misses) + len(r.base_misses) for r in rs)
        infra = sum(len(r.head_infra) + len(r.base_infra) for r in rs)
        lines.append(f"| {_runner_label(runner)} | {suite} | " + " | ".join(cells) + f" | {misses} | {infra} |")
    return lines


def _row_table(rows: list[Row], versions: list[str], label: str) -> list[str]:
    lines = [
        f"| {label} | suite | runner | " + " | ".join(versions) + " | note |",
        "|---|---|---|" + "---|" * (len(versions) + 1),
    ]
    for row in sorted(rows, key=lambda r: (r.suite, r.name, r.runner)):
        lines.append(
            f"| {row.name} | {row.suite} | {_runner_label(row.runner)} | "
            + " | ".join(_cells(row, versions))
            + f" | {_row_note(row)} |"
        )
    return lines


def _ms(value: float) -> str:
    return "–" if math.isnan(value) else f"{value:.0f}"


def _timing_compare(runs: list[dict[str, Any]]) -> list[str]:
    phases = ("step",) + STEP_TIMINGS
    lines = [
        "| runner | version | runs | " + " | ".join(f"{p} p50" for p in phases) + " | wall/run | model cost |",
        "|---|---|---|" + "---|" * (len(phases) + 2),
    ]
    by: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in runs:
        by[(r["runner"], r["version"])].append(r)
    for (runner, version), rs in sorted(by.items()):
        s = summary(rs)
        cells = [_ms(s["p50_step"])] + [_ms(s[k + "_p50"]) for k in STEP_TIMINGS]
        wall = "–" if math.isnan(s["wall"]) else f"{s['wall']:.1f} s"
        lines.append(
            f"| {runner} | {version} | {len(rs)} | " + " | ".join(cells) + f" | {wall} | "
            f"${s['decide_cost_total'] + s['writer_cost_total']:.3f} |"
        )
    return lines


def _shard_table(meta: list[dict[str, Any]]) -> list[str]:
    timings = sorted((m for m in meta if m["file"].startswith("timing-")), key=lambda m: m["file"])
    if not timings:
        return []
    lines = [
        "| shard | runs | runs at once | wall | slowest run | load average max / mean (cores) |",
        "|---|---|---|---|---|---|",
    ]
    for m in timings:
        slowest = max((r for r in m["runs"] if "seconds" in r), key=lambda r: r["seconds"], default=None)
        slow = f"{slowest['seconds']:.0f} s ({slowest['file']})" if slowest else "–"
        lines.append(
            f"| {m['shard']} | {len(m['jobs'])} | {m['concurrency']} | {m['wall_s'] / 60:.1f} min | {slow} | "
            f"{m['load_max']} / {m['load_mean']} ({m['cpu_count']}) |"
        )
    return lines


def ci_summary(
    runs: list[dict[str, Any]], probe_runs: list[dict[str, Any]], meta: list[dict[str, Any]], verdict: Verdict
) -> str:
    """The job summary: verdict, base against head per suite, timings, shards; per task and probe folded."""
    versions = [v for v in ("base", "head") if any(r["version"] == v for r in runs + probe_runs)]
    plans = [m for m in meta if m["file"].startswith("plan-")]
    trees: dict[str, str | None] = {}
    for m in plans:
        trees.update(m.get("trees") or {})
    plan = plans[0] if plans else {}
    heads = " · ".join(f"{name} `{(sha or '?')[:10]}`" for name, sha in trees.items())
    lines = [
        f"## act bench: {'pass' if verdict.ok else 'FAIL'}",
        "",
        f"{heads} · runners {', '.join(plan.get('runners', []))} · suites {', '.join(plan.get('suites') or ['all'])} · "
        f"{plan.get('repeats', 1)} repeat(s) · {len(plans)} shard(s)",
        "",
    ]
    if verdict.failures:
        lines += ["### Failed rules", ""] + [f"- {f}" for f in verdict.failures] + [""]
    if verdict.warnings:
        lines += ["### Did worse on head (listed; not failing on its own)", ""] + [f"- {w}" for w in verdict.warnings]
        lines.append("")
    trows, prows = task_rows(runs), probe_rows(probe_runs)
    if trows:
        lines += ["### Tasks", ""] + _suite_table(trows, versions) + [""]
    if prows:
        lines += ["### Probes", ""] + _suite_table(prows, versions) + [""]
    if runs:
        lines += ["### Timings (ms)", ""] + _timing_compare(runs) + [""]
    shards = _shard_table(meta)
    if shards:
        lines += ["### Shards", ""] + shards + [""]
    if trows:
        lines += ["<details><summary>Per task</summary>", ""] + _row_table(trows, versions, "task")
        lines += ["", "</details>", ""]
    if prows:
        lines += ["<details><summary>Per probe</summary>", ""] + _row_table(prows, versions, "probe")
        lines += ["", "</details>", ""]
    lines += ["<details><summary>Rules</summary>", "", RULES, "", "</details>", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directories", nargs="+")
    parser.add_argument("--tasks", default="")
    parser.add_argument("--runners", default="")
    parser.add_argument("--failures", action="store_true")
    parser.add_argument("--suite", default="")
    parser.add_argument("--no-probes", action="store_true")
    parser.add_argument("--summary", help="write the base-against-head summary (Markdown) to this file")
    parser.add_argument("--check", action="store_true", help="exit 1 when the pass/fail rules fail")
    args = parser.parse_args()
    directories = [Path(d) for d in args.directories]
    runs, probe_runs, meta = load(directories)
    if args.tasks:
        runs = [r for r in runs if r["task"] in args.tasks.split(",")]
    if args.runners:
        runs = [r for r in runs if r["runner"] in args.runners.split(",")]
        probe_runs = [r for r in probe_runs if r["runner"] in args.runners.split(",")]
    if args.suite:
        runs = [r for r in runs if r.get("suite") == args.suite]
        probe_runs = [r for r in probe_runs if r.get("suite") == args.suite]
    if args.no_probes:
        probe_runs = []
    with_base = any(r["version"] == "base" for r in runs + probe_runs)
    verdict = judge(runs, probe_runs, missing_runs(directories, meta), with_base)
    if args.summary:
        _ = Path(args.summary).write_text(ci_summary(runs, probe_runs, meta, verdict))
    else:
        print(tables(runs, probe_runs, args.failures))
        print()
        print("verdict:", "pass" if verdict.ok else "FAIL")
        for line in verdict.failures:
            print("  -", line)
    if args.check and not verdict.ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
