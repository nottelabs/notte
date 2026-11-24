from scripts import generate_types_all as gen


def test_committed_types_all_is_up_to_date() -> None:
    source = gen.TYPES_MODULE.read_text()
    assert gen.render(source) == source, "run: uv run --no-sync python scripts/generate_types_all.py"


def test_exports_definitions_and_explicit_reexports_only() -> None:
    source = (
        "import os\n"
        "from pathlib import Path\n"
        "from notte_core.data import DataSpace as DataSpace\n"
        "from notte_core.config import config\n"
        "LIMIT = 10\n"
        "Alias: type[int] = int\n"
        "class Model: ...\n"
        "def helper() -> None: ...\n"
        "_private = 1\n"
    )
    assert gen.exported_names(source) == ["Alias", "DataSpace", "LIMIT", "Model", "helper"]


def test_render_appends_then_replaces_the_block() -> None:
    first = gen.render("class A: ...\n")
    assert first.endswith('__all__ = [\n    "A",\n]\n')
    second = gen.render(first.replace("class A: ...", "class A: ...\nclass B: ..."))
    assert second.count("__all__ = [") == 1
    assert '    "B",\n' in second
