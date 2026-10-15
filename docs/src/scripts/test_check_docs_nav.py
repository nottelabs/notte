"""Check reachability through both authored pages and imported partials."""

import tempfile
import unittest
from pathlib import Path

from check_docs_nav import unreferenced_snippets


class SnippetReachabilityTest(unittest.TestCase):
    def test_reports_only_snippets_without_imports(self):
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory)
            (src / "snippets").mkdir()
            used = src / "snippets/used.mdx"
            unused = src / "snippets/unused.mdx"
            partial = src / "snippets/partial.mdx"
            used.write_text("example")
            unused.write_text("unused")
            partial.write_text("import Used from '/snippets/used.mdx';\n<Used />\n")
            (src / "index.mdx").write_text('import Partial from "/snippets/partial.mdx";\n<Partial />\n')
            self.assertEqual(unreferenced_snippets(src), [unused])


if __name__ == "__main__":
    unittest.main()
