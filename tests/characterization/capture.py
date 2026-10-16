"""Subprocess entry point: preserve full hash-based selectors with PYTHONHASHSEED=0.

The parent pytest process supplies the offline configuration from tests/conftest.py.
No fields, including the process-seeded notte_selector, are scrubbed from snapshots.
"""

import argparse
import asyncio
import json
from pathlib import Path

import notte
from tests.characterization.pages import load
from tests.characterization.snapshots import render_actions
from tests.golden.test_golden_pages import BASE_URL, _serve


async def capture(fixture: str, saved_page: bool) -> tuple[str, str]:
    observations: list[tuple[str, str]] = []
    for _ in range(1 if saved_page else 2):
        async with notte.Session(headless=True, viewport_width=1280, viewport_height=720) as session:
            if saved_page:
                await session.window.page.route("**/*", _serve)
                _ = await session.window.page.goto(f"{BASE_URL}{fixture}")
            else:
                await load(session, fixture)
            for _ in range(1 if saved_page else 3):
                observation = await session.aobserve()
                assert observation.space.interaction_actions, fixture
                observations.append((observation.space.description, render_actions(observation)))
    assert all(item == observations[0] for item in observations), f"{fixture} is not deterministic"
    return observations[0]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("fixture")
    _ = parser.add_argument("output", type=Path)
    _ = parser.add_argument("--saved-page", action="store_true")
    args = parser.parse_args()
    description, actions = asyncio.run(capture(args.fixture, args.saved_page))
    _ = args.output.write_text(
        json.dumps(
            {"fixture": args.fixture, "saved_page": args.saved_page, "description": description, "actions": actions}
        )
    )
