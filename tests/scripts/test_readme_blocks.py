"""Exercise README block extraction without touching the real README."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).parents[2]
spec = importlib.util.spec_from_file_location("readme_blocks", ROOT / "scripts/readme_blocks.py")
assert spec and spec.loader
readme_blocks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(readme_blocks)

FENCE = "```"


def write_readme(tmp_path: Path, body: str) -> Path:
    readme = tmp_path / "README.md"
    _ = readme.write_text(body.replace("~~~", FENCE))
    return readme


def test_blocks_filters_by_language_and_reports_line(tmp_path: Path):
    readme = write_readme(tmp_path, "# Title\n\n~~~python\nprint(1)\n~~~\n\n~~~bash\necho hi\n~~~\n")
    assert readme_blocks.blocks(readme, {"python"}) == [(3, "print(1)\n")]
    assert readme_blocks.blocks(readme, {"bash"}) == [(7, "echo hi\n")]


def test_blocks_ignores_fence_info_after_language(tmp_path: Path):
    readme = write_readme(tmp_path, '~~~python requires-env="X"\nx = 1\n~~~\n')
    assert readme_blocks.blocks(readme, {"python"}) == [(1, "x = 1\n")]


def test_extract_with_no_typescript_writes_empty_config(tmp_path: Path):
    readme = write_readme(tmp_path, "~~~python\nx = 1\n~~~\n")
    out = tmp_path / "out"
    assert readme_blocks.extract(readme, out) == []
    assert json.loads((out / "tsconfig.json").read_text())["files"] == []


def test_extract_writes_typescript_and_removes_stale_files(tmp_path: Path):
    readme = write_readme(tmp_path, "intro\n~~~typescript\nconst a = 1;\n~~~\n")
    out = tmp_path / "out"
    out.mkdir()
    _ = (out / "readme_L99.mts").write_text("stale")
    assert readme_blocks.extract(readme, out) == ["readme_L2.mts"]
    assert sorted(p.name for p in out.glob("*.mts")) == ["readme_L2.mts"]
    assert (out / "readme_L2.mts").read_text() == "const a = 1;\n"


def test_syntax_errors_reports_python_and_shell(tmp_path: Path):
    readme = write_readme(tmp_path, "~~~python\ndef (:\n~~~\n~~~bash\nif then\n~~~\n~~~python\nok = 1\n~~~\n")
    errors = readme_blocks.syntax_errors(readme)
    assert len(errors) == 2
    assert errors[0].startswith("README.md:1: Python syntax error")
    assert errors[1].startswith("README.md:4: shell syntax error")


def test_setup_commands_joins_continuations_and_strips_comments(tmp_path: Path):
    readme = write_readme(
        tmp_path,
        "~~~bash\npip install notte-sdk   # or: npm install notte-sdk\n"
        "pip install \\\n  notte \\\n  playwright\ncurl https://example.com\n~~~\n"
        "~~~\npatchright install --with-deps chromium\n~~~\n"
        "~~~python\npip install not-a-shell-block\n~~~\n",
    )
    assert readme_blocks.setup_commands(readme) == [
        "pip install notte-sdk",
        "pip install notte playwright",
        "patchright install --with-deps chromium",
    ]


def test_setup_commands_does_not_merge_unrelated_lines(tmp_path: Path):
    readme = write_readme(tmp_path, "~~~bash\n# install\nnpm install notte-sdk\necho done\n~~~\n")
    assert readme_blocks.setup_commands(readme) == ["npm install notte-sdk"]
