"""Exercise the published MySQL guide sources without external credentials."""

import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SOURCE = Path(__file__).resolve().parents[1] / "testers/guides/mysql"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SOURCE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class MysqlGuideTest(unittest.TestCase):
    def setUp(self):
        self.modules = patch.dict(sys.modules)
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.driver = types.ModuleType("pymysql")
        self.driver.connect = MagicMock()
        sys.modules["pymysql"] = self.driver
        self.handler = load("scrape_function")
        self.writer = load("scrape_to_mysql")
        self.env = patch.dict(
            os.environ,
            {
                "NOTTE_API_KEY": "fixture-notte-key",
                "NOTTE_API_URL": "https://notte.example",
                "MYSQL_INGEST_URL": "https://receiver.example/ingest",
                "MYSQL_INGEST_TOKEN": "fixture-ingest-token",
                "MYSQL_HOST": "mysql.example",
                "MYSQL_USER": "writer",
                "MYSQL_PASSWORD": "fixture-mysql-password",
                "MYSQL_DATABASE": "scrapes",
            },
            clear=True,
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    def response(self, body, status=200):
        response = MagicMock(status_code=status)
        response.json.return_value = body
        return response

    def test_hosted_handler_posts_validated_data_and_requires_a_write_acknowledgement(self):
        extracted = {"title": "Example Domain", "description": "Documentation example"}
        scrape = self.response({"structured": {"success": True, "data": extracted}})
        for acknowledged in (True, False):
            with self.subTest(acknowledged=acknowledged):
                with patch.object(
                    self.handler.requests, "post", side_effect=[scrape, self.response({"saved": acknowledged})]
                ) as post:
                    if acknowledged:
                        self.assertEqual(
                            self.handler.run("https://example.com"), {"url": "https://example.com", "saved": True}
                        )
                    else:
                        with self.assertRaisesRegex(RuntimeError, "confirm"):
                            self.handler.run("https://example.com")
                    self.assertEqual(post.call_args_list[0].args, ("https://notte.example/scrape",))
                    self.assertEqual(post.call_args.kwargs["json"], {"url": "https://example.com", "data": extracted})
                    self.assertFalse(post.call_args.kwargs["allow_redirects"])

    def test_failed_extraction_never_contacts_receiver(self):
        with patch.object(
            self.handler.requests, "post", return_value=self.response({"structured": {"success": False}})
        ) as post:
            with self.assertRaisesRegex(RuntimeError, "structured data"):
                self.handler.run("https://example.com")
            self.assertEqual(post.call_count, 1)

    def test_receiver_requires_https_before_scraping(self):
        os.environ["MYSQL_INGEST_URL"] = "http://receiver.example/ingest"
        with patch.object(self.handler.requests, "post") as post:
            with self.assertRaisesRegex(ValueError, "HTTPS"):
                self.handler.run("https://example.com")
            post.assert_not_called()

    def test_receiver_rejects_missing_or_invalid_tokens_without_writing(self):
        from fastapi.testclient import TestClient

        receiver = load("mysql_receiver")
        payload = {"url": "https://example.com/Report", "data": {"title": "Report", "description": "Page"}}
        with TestClient(receiver.app) as client, patch.object(receiver, "save_page") as save:
            for headers in ({}, {"Authorization": "Bearer wrong"}):
                with self.subTest(headers=headers):
                    self.assertEqual(client.post("/ingest", json=payload, headers=headers).status_code, 401)
            save.assert_not_called()

    def test_receiver_preserves_url_and_writes_once_with_correct_token(self):
        from fastapi.testclient import TestClient

        receiver = load("mysql_receiver")
        payload = {"url": "https://example.com/Report", "data": {"title": "Report", "description": "Page"}}
        with TestClient(receiver.app) as client, patch.object(receiver, "save_page") as save:
            response = client.post("/ingest", json=payload, headers={"Authorization": "Bearer fixture-ingest-token"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"saved": True})
            save.assert_called_once()
            self.assertEqual(save.call_args.args[0], payload["url"])
            self.assertEqual(save.call_args.args[1].model_dump(), payload["data"])

    def test_writer_parameterizes_values_commits_once_and_closes(self):
        connection = self.driver.connect.return_value
        page = self.handler.PageData(title="Quote ' and %s", description="A description")
        self.writer.save_page("https://example.com", page)
        statement, values = connection.cursor.return_value.__enter__.return_value.execute.call_args.args
        self.assertNotIn(page.title, statement)
        self.assertEqual(values, ("https://example.com", page.title, page.description, page.title, page.description))
        connection.commit.assert_called_once_with()
        connection.close.assert_called_once_with()
        tls = self.driver.connect.call_args.kwargs["ssl"]
        self.assertTrue(tls.check_hostname)

    def test_failed_write_does_not_commit_and_closes_connection(self):
        connection = self.driver.connect.return_value
        connection.cursor.return_value.__enter__.return_value.execute.side_effect = RuntimeError(
            "fixture write failure"
        )
        with self.assertRaisesRegex(RuntimeError, "fixture write failure"):
            self.writer.save_page(
                "https://example.com", self.handler.PageData(title="Example", description="Description")
            )
        connection.commit.assert_not_called()
        connection.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
