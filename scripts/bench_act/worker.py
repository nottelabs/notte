# pyright: basic
"""Run one job of `bench.py` (a task or a probe page, one runner, one repeat) and write its run file.

`bench.py` starts it in the environment of the code under test (`uv run --no-sync python` in that tree), so each run
has its own process, browser and session:

    python scripts/bench_act/worker.py --job '{"runner": "notte-local", "kind": "task", "names": ["search"], ...}' \
        --fixtures http://127.0.0.1:PORT --out /tmp/act-bench/head/notte-local__search__1.json
"""

import sys
from pathlib import Path

if not __package__:  # run as a script: import the harness as the `bench_act` package
    sys.path[0] = str(Path(__file__).resolve().parents[1])
    __package__ = "bench_act"

import argparse  # noqa: E402
import asyncio  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import time  # noqa: E402
import traceback  # noqa: E402
from typing import Any  # noqa: E402

from .model import FIXTURES  # noqa: E402
from .registry import discover  # noqa: E402
from .rules import probe_site_miss, site_miss, stop_reason  # noqa: E402
from .runners import WRITER, labels, run_probes, run_task  # noqa: E402


def redact(text: str) -> str:
    for name in ("OPENROUTER_API_KEY", "NOTTE_API_KEY"):
        value = os.environ.get(name)
        if value:
            text = text.replace(value, "[REDACTED]")
    return text


def run_job(job: dict[str, Any], fixtures: str) -> dict[str, Any]:
    registry = discover()
    runner = job["runner"]
    kind = runner.rsplit("-", 1)[-1] if runner.endswith(("-llm", "-scripted")) else "jev"
    record: dict[str, Any] = {
        "version": job["version"],
        "sha": job.get("sha"),
        "runner": runner,
        "repeat": job["repeat"],
        "suite": job["suite"],
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if job["kind"] == "probes":
        probes = [registry.probes[name] for name in job["names"]]
        record.update(url=probes[0].url, names=job["names"])
        try:
            record.update(asyncio.run(run_probes(probes, probes[0].url.replace(FIXTURES, fixtures), kind)))
        except Exception as e:
            record["error"] = f"{type(e).__name__}: {e}"[:1000]
            record["traceback"] = traceback.format_exc()[-3000:]
        # a page that was not there to be asked about makes its probes site misses, not wrong answers
        record["site_miss"] = probe_site_miss(probes[0].url, record)
        for p in record.get("probes", []):
            p["site_miss"] = record["site_miss"] is not None
        return record
    task = registry.tasks[job["names"][0]]
    record.update(task=task.name, url=task.url, goal=task.goal, writer=WRITER)
    try:
        record.update(asyncio.run(run_task(task, task.url.replace(FIXTURES, fixtures), kind, labels(runner))))
    except Exception as e:
        record["error"] = f"{type(e).__name__}: {e}"[:1000]
        record["traceback"] = traceback.format_exc()[-3000:]
    final = record.get("final")
    try:
        record["success"] = bool(final) and task.check(final, record)
    except Exception as e:
        record["success"] = False
        record["check_error"] = f"{type(e).__name__}: {e}"[:1000]
    record["stop_reason"] = stop_reason(record, task.max_steps)
    record["site_miss"] = site_miss(task.url, record)
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True, help="the job, as JSON (see bench.py)")
    parser.add_argument("--fixtures", required=True, help="base URL of the fixture server")
    parser.add_argument("--out", required=True, help="the run file to write")
    args = parser.parse_args()
    record = run_job(json.loads(args.job), args.fixtures)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    _ = out.write_text(redact(json.dumps(record, indent=1, default=str)))


if __name__ == "__main__":
    main()
