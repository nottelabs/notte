#!/bin/bash
set -euo pipefail

rm -rf .venv
uv venv --python 3.11
source .venv/bin/activate
uv pip install --upgrade pip
uv pip install --upgrade notte-sdk pytest-examples==0.0.17
uv pip install --upgrade patchright
uv run patchright install
uv run pytest tests/test_snippets.py -v --tb=short
rm cookies.json
rm replay.webp
