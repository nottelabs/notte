import json
import tempfile
import unittest
from pathlib import Path

from live import check_live_contracts


class LiveContractTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.testers = Path(self.temp.name)
        (self.testers / "example.py").write_text('print("hello")\n')
        (self.testers / "example.ts").write_text('console.log("hello");\n')
        self.contracts = {"example.ts": {"expected": {"status": "closed"}}}

    def check(self, contracts):
        return check_live_contracts(self.testers, contracts, dedicated=set())

    def test_requires_behavior_assertions_for_every_executable_pair(self):
        self.assertEqual(self.check(self.contracts), [])
        self.assertIn("Executable pair needs a behavior contract: example.ts", self.check({}))

    def test_rejects_missing_python_counterpart(self):
        (self.testers / "example.py").unlink()
        self.assertTrue(self.check(self.contracts))

    def test_rejects_pending_python_counterpart(self):
        (self.testers / "snippets.json").write_text(
            json.dumps({"example.mdx": {"blocks": [{"source": "example.py", "execution_pending": "Needs fixtures"}]}})
        )
        self.assertTrue(self.check(self.contracts))

    def test_rejects_stale_contract(self):
        (self.testers / "example.ts").unlink()
        self.assertTrue(self.check(self.contracts))

    def test_rejects_empty_or_misspelled_assertions(self):
        for contract in ({}, {"expected": {}}, {"expected": {"status": "closed"}, "closedSesion": True}):
            with self.subTest(contract=contract):
                self.assertTrue(self.check({"example.ts": contract}))

    def test_repository_contracts_are_complete(self):
        directory = Path(__file__).resolve().parent
        self.assertEqual(
            check_live_contracts(
                directory.parent / "testers", json.loads((directory / "live-examples.json").read_text())
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
