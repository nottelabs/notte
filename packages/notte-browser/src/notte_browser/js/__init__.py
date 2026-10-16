"""Standalone page scripts shared by browser operations."""

from functools import cache
from pathlib import Path


@cache
def script(name: str) -> str:
    return (Path(__file__).parent / name).read_text(encoding="utf-8")
