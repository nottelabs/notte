"""Compare conversion memory in fresh subprocesses; run with `uv run python`.

Synthetic graphs demonstrate the serializer mechanism, not any incident's cause.
The parent samples RSS independently of the child's GIL and stops at 1.5 GiB/30s.
Input allocation precedes the baseline. Output is never sent to the parent.
"""

import json
import os
import resource
import subprocess
import sys
import time

import psutil

LIMIT = 16 * 1024 * 1024
CASES = ("original_graph", "bounded_graph", "escaped_string", "exact_limit")


def child(case: str) -> None:
    from notte_browser.evaluation_result import format_evaluation_result
    from notte_core.errors.actions import EvaluateJsResultLimitError

    if case.endswith("graph"):
        value = {"value": "x"}
        for _ in range(18):
            value = {"left": value, "right": value}
    elif case == "escaped_string":
        value = ["\x00" * LIMIT]
    else:
        value = ["a" * (LIMIT - 8)]  # '[\n  "' + content + '"\n]'
    baseline = psutil.Process().memory_info().rss
    print(json.dumps({"baseline_rss": baseline}), flush=True)
    _ = sys.stdin.readline()
    start = time.monotonic()
    try:
        result = (
            json.dumps(value, indent=2, default=str)
            if case == "original_graph"
            else format_evaluation_result(value, max_bytes=LIMIT)
        )
        outcome = {"status": "returned", "output_bytes": len(result)}
    except EvaluateJsResultLimitError:
        outcome = {"status": "limited"}
    high_water = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    high_water_bytes = high_water if sys.platform == "darwin" else high_water * 1024
    print(json.dumps({**outcome, "seconds": time.monotonic() - start, "high_water_rss": high_water_bytes}), flush=True)
    time.sleep(0.1)


def main() -> None:
    for case in CASES:
        with subprocess.Popen(
            [sys.executable, __file__, case],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            env={**os.environ, "DISABLE_TELEMETRY": "true"},
        ) as process:
            assert process.stdout is not None and process.stdin is not None
            baseline = json.loads(process.stdout.readline())["baseline_rss"]
            peak = baseline
            started = time.monotonic()
            _ = process.stdin.write("go\n")
            process.stdin.flush()
            observed = psutil.Process(process.pid)
            while process.poll() is None:
                try:
                    peak = max(peak, observed.memory_info().rss)
                except psutil.NoSuchProcess:
                    break
                if peak > 1536 * 1024**2 or time.monotonic() - started > 30:
                    process.kill()
                    raise RuntimeError(f"{case} exceeded experiment budget")
                time.sleep(0.005)
            if process.wait() != 0:
                raise RuntimeError(f"{case} failed")
            outcome = json.loads(process.stdout.readline())
            print(
                json.dumps(
                    {
                        "case": case,
                        "baseline_rss": baseline,
                        "peak_rss": peak,
                        "additional_rss": peak - baseline,
                        **outcome,
                    }
                ),
                flush=True,
            )


if __name__ == "__main__":
    if len(sys.argv) == 2:
        child(sys.argv[1])
    else:
        main()
