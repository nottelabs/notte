"""Summarize provider matrix JUnit properties without workspace dependencies."""

from __future__ import annotations

import statistics
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path


def summarize(path: Path) -> str:
    routes: dict[str, list[tuple[dict[str, str], str, str]]] = defaultdict(list)
    for case in ET.parse(path).iter("testcase"):
        props = {p.attrib["name"]: p.attrib["value"] for p in case.findall("properties/property")}
        if "route" not in props:
            continue
        skipped = case.find("skipped")
        failed = case.find("failure")
        error = case.find("error")
        status = "skip" if skipped is not None else "fail" if failed is not None or error is not None else "pass"
        reason = skipped.attrib.get("message", "") if skipped is not None else ""
        routes[props["route"]].append((props, status, reason))
    if not routes:
        raise ValueError("JUnit contains no provider matrix results")
    lines = [
        "### Local LLM provider matrix",
        "",
        "| Route | Model / upstream | Pass / skip / fail | Response-format paths | Median latency |",
        "| --- | --- | --- | --- | --- |",
    ]
    reasons: set[str] = set()
    for route, rows in sorted(routes.items()):
        props = rows[0][0]
        counts = " / ".join(
            str(sum(status == expected for _, status, _ in rows)) for expected in ("pass", "skip", "fail")
        )
        paths = "; ".join(sorted({p["format_path"] for p, _, _ in rows}))
        times = [float(p["latency_seconds"]) for p, status, _ in rows if status == "pass"]
        latency = f"{statistics.median(times):.3f}s" if times else "—"
        model = props.get("resolved_model", props["model"])
        lines.append(f"| {route} | {model} / {props['upstream']} | {counts} | {paths} | {latency} |")
        reasons.update(f"- {route}/{p['case']}: {reason}" for p, _, reason in rows if reason)
    if reasons:
        lines += ["", "Skip reasons:", "", *sorted(reasons)]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    print(summarize(Path(sys.argv[1])), end="")
