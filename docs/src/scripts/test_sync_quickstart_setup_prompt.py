"""Exercise the setup synchronizer's CLI against isolated documentation files."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

SOURCE = Path(__file__).with_name("sync_quickstart_setup_prompt.py")
QUICKSTART = SOURCE.parent.parent / "quickstart.mdx"
PROMPT = "Read https://notte.cc/skill.md and follow its setup instructions."
ENCODED = quote(PROMPT, safe="")


class SetupPromptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        scripts = root / "scripts"
        scripts.mkdir()
        self.script = scripts / SOURCE.name
        shutil.copyfile(SOURCE, self.script)
        self.page = root / "quickstart.mdx"
        self.original = QUICKSTART.read_text(encoding="utf-8")
        self.page.write_text(self.original, encoding="utf-8")

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.script), *args],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    def test_current_prompt_passes_without_writing(self) -> None:
        before = self.page.stat().st_mtime_ns
        for args in [("--check",), ()]:
            result = self.run_cli(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.page.stat().st_mtime_ns, before)

    def assert_drift_detected_and_repaired(self, stale: str) -> None:
        self.page.write_text(stale, encoding="utf-8")
        check = self.run_cli("--check")
        self.assertEqual(check.returncode, 1)
        self.assertIn("out of date", check.stdout)
        self.assertEqual(self.page.read_text(encoding="utf-8"), stale)

        repair = self.run_cli()
        self.assertEqual(repair.returncode, 0, repair.stderr)
        self.assertEqual(self.page.read_text(encoding="utf-8"), self.original)
        self.assertEqual(self.run_cli("--check").returncode, 0)

    def test_each_surface_detects_drift_and_can_be_repaired(self) -> None:
        # Four menu items copy the prompt, the preview shows it, and agents read it.
        parts = self.original.split(PROMPT)
        self.assertEqual(len(parts), 7, "menu copies, preview, and agent output must all be covered")
        for surface in range(len(parts) - 1):
            with self.subTest(surface=surface):
                stale = parts[0]
                for index, part in enumerate(parts[1:]):
                    stale += ("Outdated setup instructions." if index == surface else PROMPT) + part
                self.assert_drift_detected_and_repaired(stale)

    def test_each_deep_link_detects_drift_and_can_be_repaired(self) -> None:
        # Claude Code and Cursor receive the prompt URL-encoded.
        parts = self.original.split(ENCODED)
        self.assertEqual(len(parts), 3, "both deep links must be covered")
        for link in range(2):
            with self.subTest(link=link):
                stale = parts[0]
                for index, part in enumerate(parts[1:]):
                    stale += ("Outdated%20setup" if index == link else ENCODED) + part
                self.assert_drift_detected_and_repaired(stale)

    def test_missing_surface_fails_without_partial_writes(self) -> None:
        for marker, message in [
            ("data-nv-copy-prompt=", "expected to replace at least one"),
            ('href="claude-cli://open?q=', "expected to replace exactly one"),
            ('href="https://cursor.com/link/prompt?text=', "expected to replace exactly one"),
            ('<div className="nv-qs__prompt">', "expected to replace exactly one"),
            ('<Visibility for="agents">', "expected to replace exactly one"),
        ]:
            with self.subTest(marker=marker):
                malformed = self.original.replace(marker, "REMOVED")
                self.page.write_text(malformed, encoding="utf-8")
                for args in [("--check",), ()]:
                    result = self.run_cli(*args)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn(message, result.stderr)
                    self.assertEqual(self.page.read_text(encoding="utf-8"), malformed)

    def test_missing_file_is_an_error(self) -> None:
        self.page.unlink()
        result = self.run_cli("--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("failed to update", result.stderr)
        self.assertFalse(self.page.exists())


if __name__ == "__main__":
    unittest.main()
