"""Exercise the CLI reference sync: navigation, change detection, and llms.txt."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))

import generate_cli_reference as gen  # noqa: E402

PAGES = ["cli-reference/index", "cli-reference/auth", "cli-reference/sessions", "cli-reference/other"]


def docs_with_tabs(*tabs: dict[str, Any]) -> dict[str, Any]:
    return {"navigation": {"tabs": list(tabs)}}


class SyncNavTests(unittest.TestCase):
    def test_inserts_cli_tab_after_apis_and_sdks(self) -> None:
        docs = docs_with_tabs({"tab": "Documentation"}, {"tab": "APIs and SDKs"}, {"tab": "Resources"})
        gen.sync_nav(docs, PAGES)
        names = [t["tab"] for t in docs["navigation"]["tabs"]]
        self.assertEqual(names, ["Documentation", "APIs and SDKs", "CLI", "Resources"])

    def test_replaces_existing_cli_tab(self) -> None:
        stale = {"tab": "CLI", "groups": [{"group": "Commands", "pages": ["cli-reference/removed"]}]}
        docs = docs_with_tabs({"tab": "APIs and SDKs"}, stale, {"tab": "Resources"})
        gen.sync_nav(docs, PAGES)
        tabs = docs["navigation"]["tabs"]
        self.assertEqual([t["tab"] for t in tabs], ["APIs and SDKs", "CLI", "Resources"])
        self.assertNotIn("cli-reference/removed", str(tabs[1]))

    def test_splits_overview_from_commands(self) -> None:
        docs = docs_with_tabs({"tab": "APIs and SDKs"})
        gen.sync_nav(docs, PAGES)
        groups = docs["navigation"]["tabs"][1]["groups"]
        self.assertEqual(groups[0], {"group": "Getting Started", "pages": ["cli-reference/index"]})
        self.assertEqual(groups[1], {"group": "Commands", "pages": PAGES[1:]})


class NavPagesTests(unittest.TestCase):
    def test_overview_first_and_other_last(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for name in ["vaults", "other", "auth", "index", "sessions"]:
                (Path(tmp) / f"{name}.mdx").write_text("x\n")
            pages = gen.nav_pages(Path(tmp))
        self.assertEqual(
            pages,
            [f"cli-reference/{n}" for n in ["index", "auth", "sessions", "vaults", "other"]],
        )


class SameTreeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.a = Path(self.temp.name) / "a"
        self.b = Path(self.temp.name) / "b"
        for d in (self.a, self.b):
            d.mkdir()
            (d / "auth.mdx").write_text("same\n")

    def test_identical_trees_match(self) -> None:
        self.assertTrue(gen.same_tree(self.a, self.b))

    def test_changed_page_is_detected(self) -> None:
        (self.b / "auth.mdx").write_text("changed\n")
        self.assertFalse(gen.same_tree(self.a, self.b))

    def test_added_or_missing_page_is_detected(self) -> None:
        (self.b / "vaults.mdx").write_text("new\n")
        self.assertFalse(gen.same_tree(self.a, self.b))
        self.assertFalse(gen.same_tree(self.b, self.a))

    def test_missing_directory_does_not_match(self) -> None:
        self.assertFalse(gen.same_tree(Path(self.temp.name) / "absent", self.b))


class PresentationTests(unittest.TestCase):
    def test_product_icons_follow_site_mapping(self) -> None:
        self.assertEqual(
            gen.normalize_icons('<Card icon="code" title="Functions"><Card icon="browser" title="Sessions">'),
            '<Card icon="flower" title="Functions"><Card icon="tv" title="Sessions">',
        )

    def test_llms_check_detects_missing_stale_and_duplicate_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fresh = Path(tmp)
            (fresh / "index.mdx").write_text('---\ntitle: "CLI"\ndescription: "New description"\n---\n')
            current = "- [CLI](https://docs.notte.cc/cli-reference/index.md): New description"
            self.assertTrue(gen.cli_llms_matches(fresh, current))
            for stale in ("", current.replace("New", "Old"), current + "\n" + current):
                with self.subTest(stale=stale):
                    self.assertFalse(gen.cli_llms_matches(fresh, stale))


class RegenerateTests(unittest.TestCase):
    """main() in write mode, with the Go generator and llms.txt build stubbed."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.out_dir = root / "cli-reference"
        self.docs_json = root / "docs.json"
        patches = [
            mock.patch.object(gen, "OUT_DIR", self.out_dir),
            mock.patch.object(gen, "DOCS_JSON", self.docs_json),
            mock.patch.object(gen, "generate", self.fake_generate),
            mock.patch.object(sys, "argv", ["generate_cli_reference.py"]),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    @staticmethod
    def fake_generate(out: Path) -> None:
        for name in ["index", "auth"]:
            (out / f"{name}.mdx").write_text(f"{name}\n")

    def run_main(self) -> mock.MagicMock:
        with mock.patch.object(gen.subprocess, "run") as run:
            self.assertEqual(gen.main(), 0)
        return run

    def test_rebuilds_llms_when_navigation_is_unchanged(self) -> None:
        # A description-only CLI change leaves docs.json as is but still changes
        # llms.txt, so the rebuild must not depend on the navigation changing.
        docs = docs_with_tabs({"tab": "APIs and SDKs"})
        gen.sync_nav(docs, ["cli-reference/index", "cli-reference/auth"])
        self.docs_json.write_text(gen.json.dumps(docs, indent=2, ensure_ascii=False) + "\n")

        run = self.run_main()

        run.assert_called_once()
        self.assertIn("scripts/generate_llms.py", run.call_args.args[0])

    def test_writes_pages_and_navigation(self) -> None:
        self.docs_json.write_text(gen.json.dumps(docs_with_tabs({"tab": "APIs and SDKs"})))
        self.run_main()
        self.assertEqual(sorted(p.name for p in self.out_dir.glob("*.mdx")), ["auth.mdx", "index.mdx"])
        self.assertIn('"tab": "CLI"', self.docs_json.read_text())


if __name__ == "__main__":
    unittest.main()
