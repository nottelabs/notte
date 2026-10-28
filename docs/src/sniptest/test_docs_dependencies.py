"""Keep one copy of `zod` in the docs examples' dependencies."""

import json
import unittest
from pathlib import Path

LOCK = Path(__file__).resolve().parents[2] / "package-lock.json"


class DocsDependenciesTest(unittest.TestCase):
    def test_one_zod_copy(self):
        # A package with its own zod makes check_typescript.mjs compare two copies' schema types: it runs out of memory.
        packages = json.loads(LOCK.read_text())["packages"]
        copies = sorted(path for path in packages if path == "node_modules/zod" or path.endswith("/node_modules/zod"))
        self.assertEqual(copies, ["node_modules/zod"])


if __name__ == "__main__":
    unittest.main()
