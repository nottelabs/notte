import os
import runpy
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

EXAMPLE = Path(__file__).resolve().parent.parent / "testers/functions/management/version_history.py"


def fake_client(owned_page: int | None, total_pages: int = 3):
    calls: list[dict[str, int]] = []

    def function(function_id: str) -> SimpleNamespace:
        return SimpleNamespace(function_id=function_id, name=function_id, versions=["v1"], latest_version="v1")

    def page(number: int) -> list[SimpleNamespace]:
        size = 100 if number < total_pages else 40
        return [function("owned" if number == owned_page and i == 7 else f"other-{number}-{i}") for i in range(size)]

    def list_functions(**query: int) -> SimpleNamespace:
        if not query:
            # The displayed example lists the first page with the default size.
            return SimpleNamespace(items=[f for f in page(1)[:20] if f.function_id != "owned"], has_next=True)
        calls.append(query)
        return SimpleNamespace(items=page(query["page"]), has_next=query["page"] < total_pages)

    client = SimpleNamespace(functions=SimpleNamespace(list=list_functions))
    return client, calls


class VersionHistoryPagingTest(unittest.TestCase):
    def run_example(self, owned_page: int | None) -> tuple[dict[str, object], list[dict[str, int]]]:
        client, calls = fake_client(owned_page)
        sdk_module = ModuleType("notte_sdk")
        sdk_module.NotteClient = lambda: client  # pyright: ignore[reportAttributeAccessIssue]
        with (
            patch.dict("sys.modules", {"notte_sdk": sdk_module}),
            patch.dict(os.environ, {"NOTTE_FUNCTION_ID": "owned"}),
            patch("builtins.print"),
        ):
            return runpy.run_path(str(EXAMPLE)), calls

    def test_finds_the_owned_function_on_a_later_page(self) -> None:
        for owned_page in (1, 3):
            with self.subTest(owned_page=owned_page):
                namespace, calls = self.run_example(owned_page)
                self.assertEqual(namespace["results"], [True, True])
                self.assertIn({"page": owned_page, "page_size": 100}, calls)

    def test_fails_when_the_owned_function_is_missing(self) -> None:
        with self.assertRaises(AssertionError):
            self.run_example(owned_page=None)


if __name__ == "__main__":
    unittest.main()
