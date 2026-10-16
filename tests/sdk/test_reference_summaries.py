"""Schema types without docstrings still get useful generated reference summaries."""

import runpy
from pathlib import Path
from types import SimpleNamespace


def test_generated_run_payload_reference_summary(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    config = runpy.run_path(str(root / "docs/sphinx/conf.py"))
    page = tmp_path / "src/sdk-reference/misc/runpayloadreference.mdx"
    page.parent.mkdir(parents=True)
    page.write_text('---\ntitle: "RunPayloadReference"\ndescription: ""\n---\n')
    config["preserve_function_runtime_default"](SimpleNamespace(confdir=tmp_path / "sphinx"), None)
    assert 'description: "Identifies an uploaded run field by its size, checksum, and upload ID."' in page.read_text()
