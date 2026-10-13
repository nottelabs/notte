"""Exercise the setup synchronizer's CLI against isolated documentation files."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).with_name("sync_quickstart_setup_prompt.py")
QUICKSTART = SOURCE.parent.parent / "quickstart.mdx"
PROMPT = "Read https://notte.cc/skill.md and follow its setup instructions."


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

    def test_each_surface_detects_drift_and_can_be_repaired(self) -> None:
        parts = self.original.split(PROMPT)
        self.assertEqual(len(parts), 4, "clipboard, preview, and agent output must all be covered")
        for surface in range(3):
            with self.subTest(surface=surface):
                stale = parts[0]
                for index, part in enumerate(parts[1:]):
                    stale += ("Outdated setup instructions." if index == surface else PROMPT) + part
                self.page.write_text(stale, encoding="utf-8")
                check = self.run_cli("--check")
                self.assertEqual(check.returncode, 1)
                self.assertIn("out of date", check.stdout)
                self.assertEqual(self.page.read_text(encoding="utf-8"), stale)

                repair = self.run_cli()
                self.assertEqual(repair.returncode, 0, repair.stderr)
                self.assertEqual(self.page.read_text(encoding="utf-8"), self.original)
                self.assertEqual(self.run_cli("--check").returncode, 0)

    def test_missing_surface_fails_without_partial_writes(self) -> None:
        for marker in [
            "navigator.clipboard.writeText(notteSetupPrompt);",
            '<Accordion title="View setup prompt">',
            '<Visibility for="agents">',
        ]:
            with self.subTest(marker=marker):
                malformed = self.original.replace(marker, "REMOVED")
                self.page.write_text(malformed, encoding="utf-8")
                for args in [("--check",), ()]:
                    result = self.run_cli(*args)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("expected to replace exactly one", result.stderr)
                    self.assertEqual(self.page.read_text(encoding="utf-8"), malformed)

    def test_missing_file_is_an_error(self) -> None:
        self.page.unlink()
        result = self.run_cli("--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("failed to update", result.stderr)
        self.assertFalse(self.page.exists())


if __name__ == "__main__":
    unittest.main()
