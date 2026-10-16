"""Shipped page scripts must be valid JavaScript and have a Python consumer."""

import ast
import shutil
import subprocess
from pathlib import Path

import notte_browser.js
import pytest


def test_page_scripts_are_valid_and_loaded():
    script_dir = Path(notte_browser.js.__file__).parent
    scripts = {path.name for path in script_dir.glob("*.js")}
    loaded: set[str] = set()
    for module in script_dir.parent.rglob("*.py"):
        for node in ast.walk(ast.parse(module.read_text())):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "script"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                loaded.add(node.args[0].value)
    assert scripts
    assert scripts == loaded
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to syntax-check page scripts")
    for name in sorted(scripts):
        assert notte_browser.js.script(name) == (script_dir / name).read_text()
        subprocess.run([node, "--check", str(script_dir / name)], check=True, capture_output=True, text=True)
