"""The completed run contract shared by resume and planned-report validation (standard library only)."""

import json
from pathlib import Path

from .model import JsonValue
from .registry import PROBE_RUNNERS, TASK_RUNNERS


def read_record(path: Path) -> JsonValue:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _complete_step(step: JsonValue) -> bool:
    if not isinstance(step, dict) or not isinstance(step.get("status"), str):
        return False
    timings = step.get("timings")
    return isinstance(timings, dict) and type(timings.get("step_ms")) in (int, float)


def complete_record(record: JsonValue) -> bool:
    if not isinstance(record, dict):
        return False
    if not all(isinstance(record.get(key), str) and record[key] for key in ("suite", "url", "run_identity")):
        return False
    if record.get("version") not in ("base", "head") or "sha" not in record:
        return False
    if record["sha"] is not None and not isinstance(record["sha"], str):
        return False
    repeat = record.get("repeat")
    if type(repeat) is not int or repeat < 1:
        return False
    if any(record.get(key) is not None and not isinstance(record[key], str) for key in ("error", "site_miss")):
        return False
    runner = record.get("runner")
    if runner in TASK_RUNNERS:
        steps = record.get("steps", [])
        return (
            isinstance(record.get("task"), str)
            and isinstance(record.get("success"), bool)
            and not (record.get("error") and record["success"])
            and isinstance(record.get("stop_reason"), str)
            and ("steps" in record or bool(record.get("error")))
            and isinstance(steps, list)
            and all(_complete_step(step) for step in steps)
        )
    if runner not in PROBE_RUNNERS:
        return False
    names, probes = record.get("names"), record.get("probes", [])
    if not isinstance(names, list) or not names or not all(isinstance(name, str) for name in names):
        return False
    if not isinstance(probes, list) or not all(
        isinstance(probe, dict) and isinstance(probe.get("probe"), str) and isinstance(probe.get("correct"), bool)
        for probe in probes
    ):
        return False
    answered = [probe["probe"] for probe in probes if isinstance(probe, dict)]
    return answered == names or (bool(record.get("error")) and answered == names[: len(answered)])


def matches_plan(record: JsonValue, expected: dict[str, JsonValue]) -> bool:
    if not isinstance(record, dict) or not complete_record(record):
        return False
    if any(
        record.get(key) != expected[key]
        for key in ("version", "sha", "runner", "repeat", "suite", "url", "run_identity")
    ):
        return False
    return (
        expected["names"] == [record["task"]]
        if expected["kind"] == "task"
        else expected["names"] == record.get("names")
    )
