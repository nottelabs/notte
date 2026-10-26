# pyright: basic
"""Bench notte `act()` / `choose()` / `check()` on the tasks and probe pages of `tasks/`.

Not shipped: a dev benchmark. One run = one task with one runner, until the runner stops (DONE, BLOCKED, stale, no
progress) or the task's step cap; or the probes of one page. Success is checked on the final page, whatever the
runner claims. Each run is one process (`worker.py`) with its own browser and session, writing one JSON file;
`report.py` merges them. The fixture server is shared.

- `--concurrency N` runs N at once.
- `--shard i/n` keeps every n-th task or probe page, for a CI job matrix.
- `--tree base=PATH --tree head=PATH` runs the same harness on two checkouts, each in its own environment
  (`uv run --no-sync` there). The versions of one task run back to back (one after the other, never at once), so
  they see the same site and machine conditions. Without it, the checkout this harness is in is `head`.
- `--today YYYY-MM-DD` fixes the day the travel dates of the tasks are counted from (`model.trip_dates`), so every
  shard of a CI run asks for the same trip.
- An existing run file of the same commit is not run again: an interrupted run can be resumed.

    uv run --no-sync python scripts/bench_act/bench.py --runners notte-local,probe-local-jev --out /tmp/act-bench
    python head/scripts/bench_act/bench.py --tree base=base --tree head=head --shard 2/4 --concurrency 4 --out runs
"""

import sys
from pathlib import Path

if not __package__:  # run as a script: import the harness as the `bench_act` package
    sys.path[0] = str(Path(__file__).resolve().parents[1])
    __package__ = "bench_act"

import argparse  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import signal  # noqa: E402
import socket  # noqa: E402
import subprocess  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402
from datetime import date  # noqa: E402
from functools import partial  # noqa: E402
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402
from typing import Any  # noqa: E402

from .model import TODAY_ENV  # noqa: E402
from .registry import PROBE_RUNNERS, TASK_RUNNERS, Job, discover, pairs, parse_shard, plan, select, shard  # noqa: E402

HARNESS = Path(__file__).resolve().parent
FIXTURES = HARNESS / "fixtures"
# variables that would change the decider, the writer or the labels under the runners
CLEARED_ENV = ("TYPESAFE_API_KEY", "NOTTE_LLM_BASE_URL", "NOTTE_LLM_API_KEY", "NOTTE_LLM_MODEL")
CLEARED_PREFIX = "NOTTE_ACT_"
PRINT = threading.Lock()


def log(message: str) -> None:
    with PRINT:
        print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def default_concurrency() -> int:
    # each run is a Python process and a Chromium: about one core each while busy
    return max(1, (os.cpu_count() or 2) // 2)


def serve_fixtures() -> str:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = int(s.getsockname()[1])

    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), partial(Quiet, directory=str(FIXTURES)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{port}"


def tree_sha(tree: Path) -> str | None:
    try:
        return subprocess.check_output(["git", "-C", str(tree), "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


class LoadSampler:
    """The 1-minute load average every 10 s while the runs go."""

    def __init__(self) -> None:
        self.samples: list[float] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            self.samples.append(round(os.getloadavg()[0], 2))
            _ = self._stop.wait(10)

    def __enter__(self) -> "LoadSampler":
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join()


def kept(path: Path, sha: str | None) -> bool:
    """Resume: an existing run file is kept when it ran the same commit; one of another (or an unknown) commit is
    run again."""
    return sha is not None and json.loads(path.read_text()).get("sha") == sha


def parse_trees(specs: list[str], default: Path) -> dict[str, Path]:
    """`--tree base=PATH --tree head=PATH` -> {"base": ..., "head": ...}; no spec: this checkout is head."""
    if not specs:
        return {"head": default}
    trees: dict[str, Path] = {}
    for spec in specs:
        name, _, tree = spec.partition("=")
        if name not in ("base", "head") or name in trees or not tree:
            raise ValueError(f"--tree {spec!r}: expected base=PATH or head=PATH, each at most once")
        trees[name] = Path(tree).resolve()
    if "head" not in trees:
        raise ValueError("--tree: head=PATH is required (base=PATH is what head is compared against)")
    return {name: trees[name] for name in ("base", "head") if name in trees}


def _failed_record(job: Job, sha: str | None, error: str, log_tail: str) -> dict[str, Any]:
    """The run file of a worker that died or timed out without writing one."""
    record: dict[str, Any] = {
        "version": job.version,
        "sha": sha,
        "runner": job.runner,
        "repeat": job.repeat,
        "suite": job.item.suite,
        "error": error,
        "log_tail": log_tail,
    }
    if job.item.kind == "task":
        record.update(task=job.item.key, success=False, stop_reason="error", site_miss=None, steps=[])
    else:
        record.update(names=list(job.item.names), probes=[])
    return record


def _url(job: Job, registry_urls: dict[str, str]) -> str:
    return registry_urls[job.item.key] if job.item.kind == "task" else job.item.key


def run_job(
    job: Job,
    trees: dict[str, Path],
    shas: dict[str, str | None],
    urls: dict[str, str],
    fixtures: str,
    out: Path,
    timeout: float,
    today: str,
) -> dict[str, Any]:
    path = out / job.file
    if path.exists():
        if kept(path, shas[job.version]):
            return {"file": job.file, "skipped": True}
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    log_path = out / "_logs" / job.file.replace("/", "__").replace(".json", ".log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    spec = {
        "version": job.version,
        "sha": shas[job.version],
        "runner": job.runner,
        "kind": job.item.kind,
        "names": list(job.item.names),
        "suite": job.item.suite,
        "repeat": job.repeat,
    }
    env = {k: v for k, v in os.environ.items() if k not in CLEARED_ENV and not k.startswith(CLEARED_PREFIX)}
    env["DISABLE_TELEMETRY"] = "true"  # keep bench runs out of usage data
    env[TODAY_ENV] = today
    command = ["uv", "run", "--no-sync", "python", str(HARNESS / "worker.py"), "--job", json.dumps(spec)]
    command += ["--fixtures", fixtures, "--out", str(path)]
    start = time.perf_counter()
    error = None
    with log_path.open("w") as log_file:
        process = subprocess.Popen(
            command, cwd=trees[job.version], env=env, stdout=log_file, stderr=subprocess.STDOUT, start_new_session=True
        )
        try:
            _ = process.wait(timeout)
        except subprocess.TimeoutExpired:
            error = f"timeout: no result after {timeout:.0f} s"
            os.killpg(process.pid, signal.SIGTERM)
            try:
                _ = process.wait(15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                _ = process.wait()
    seconds = round(time.perf_counter() - start, 1)
    if not path.exists():
        tail = log_path.read_text(errors="replace")[-3000:]
        error = error or f"worker exited with code {process.returncode} without a run file"
        record = _failed_record(job, shas[job.version], error, tail)
        record["url"] = _url(job, urls)
        _ = path.write_text(json.dumps(record, indent=1))
    record = json.loads(path.read_text())
    if job.item.kind == "task":
        result = "SITE-MISS" if record.get("site_miss") else "ok" if record.get("success") else "FAIL"
        detail = f"steps={len(record.get('steps', []))} stop={record.get('stop_reason')}"
    else:
        probes = record.get("probes", [])
        result = f"{sum(bool(p.get('correct')) for p in probes)}/{len(probes)} right"
        detail = "site miss" if probes and probes[0].get("site_miss") else ""
    error = record.get("error")
    log(f"{job.file} {result} {detail} {seconds:.0f}s" + (f" error={error[:160]}" if error else ""))
    return {"file": job.file, "seconds": seconds, "returncode": process.returncode}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--runners",
        default="notte-local,probe-local-jev",
        help=f"task runners {', '.join(TASK_RUNNERS)}; probe runners {', '.join(PROBE_RUNNERS)}",
    )
    parser.add_argument("--suites", default="", help="comma-separated suites (default: all), e.g. fixtures,demo,real")
    parser.add_argument("--tasks", default="", help="only these tasks")
    parser.add_argument("--probes", default="", help="only these probes")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--shard", default="1/1", help="i/n: every n-th task or probe page, from the i-th")
    parser.add_argument("--concurrency", type=int, default=default_concurrency(), help="runs at once")
    parser.add_argument("--tree", action="append", default=[], help="NAME=PATH, a checkout to run (repeatable)")
    parser.add_argument("--job-timeout", type=float, default=900, help="seconds before a run is stopped as an error")
    parser.add_argument("--today", default="", help="YYYY-MM-DD the travel dates are counted from (default: today)")
    parser.add_argument("--dry-run", action="store_true", help="print the runs and exit")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    def names(value: str) -> list[str]:
        return [n for n in value.split(",") if n]

    runners = names(args.runners)
    for runner in runners:
        if runner not in TASK_RUNNERS + PROBE_RUNNERS:
            parser.error(f"unknown runner {runner!r}")
    try:
        trees = parse_trees(args.tree, HARNESS.parents[1])
    except ValueError as e:
        parser.error(str(e))
    today = args.today or date.today().isoformat()
    os.environ[TODAY_ENV] = today
    index, count = parse_shard(args.shard)
    registry = discover()
    items = select(
        registry,
        suites=names(args.suites),
        tasks=names(args.tasks),
        probes=names(args.probes),
        with_tasks=any(r in TASK_RUNNERS for r in runners),
        with_probes=any(r in PROBE_RUNNERS for r in runners),
    )
    jobs = plan(shard(items, index, count), runners, list(trees), args.repeats)
    if args.dry_run:
        for job in jobs:
            print(job.file)
        return

    out = Path(args.out).resolve()
    meta = out / "_meta"
    meta.mkdir(parents=True, exist_ok=True)
    label = f"shard-{index}-of-{count}"
    shas = {name: tree_sha(tree) for name, tree in trees.items()}
    plan_record = {
        "shard": f"{index}/{count}",
        "concurrency": args.concurrency,
        "runners": runners,
        "suites": names(args.suites),
        "repeats": args.repeats,
        "trees": shas,
        "today": today,
        "jobs": [job.file for job in jobs],
    }
    _ = (meta / f"plan-{label}.json").write_text(json.dumps(plan_record, indent=1))
    fixtures = serve_fixtures()
    urls = {name: task.url for name, task in registry.tasks.items()}
    log(f"{len(jobs)} runs, {args.concurrency} at once, shard {index}/{count}, trees {shas}")
    started = time.time()

    def run_pair(pair: list[Job]) -> list[dict[str, Any]]:
        return [run_job(job, trees, shas, urls, fixtures, out, args.job_timeout, today) for job in pair]

    with LoadSampler() as load, ThreadPoolExecutor(args.concurrency) as pool:
        results = [result for pair in pool.map(run_pair, pairs(jobs)) for result in pair]
    wall = round(time.time() - started, 1)
    timing = {
        **plan_record,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(started)),
        "wall_s": wall,
        "cpu_count": os.cpu_count(),
        "load_max": max(load.samples, default=None),
        "load_mean": round(sum(load.samples) / len(load.samples), 2) if load.samples else None,
        "runs": results,
    }
    _ = (meta / f"timing-{label}.json").write_text(json.dumps(timing, indent=1))
    log(f"done: {len(jobs)} runs in {wall:.0f} s, load average max {timing['load_max']} mean {timing['load_mean']}")


if __name__ == "__main__":
    main()
