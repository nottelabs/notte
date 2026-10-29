"""Provider authorization boundaries and real CLI output, without GitHub or secrets."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.ci_provider import select_provider

ROOT = Path(__file__).resolve().parents[2]
HEAD = "a" * 40
OTHER = "b" * 40
REPOSITORY = "nottelabs/notte"


def pull(**updates):
    pr = {
        "state": "open",
        "base": {"ref": "main", "repo": {"full_name": REPOSITORY}},
        "head": {"sha": HEAD, "repo": {"full_name": REPOSITORY}},
        "user": {"login": "maintainer"},
        "labels": [{"name": "ci:openai"}],
        "merged": False,
        "merge_commit_sha": OTHER,
    }
    pr.update(updates)
    return pr


def select(pulls, *, event="pull_request", attempt=2, ref="refs/pull/1214/merge", head=HEAD):
    return select_provider(event=event, ref=ref, repository=REPOSITORY, head=head, attempt=attempt, pulls=pulls)


class ProviderTests(unittest.TestCase):
    def assert_provider(self, value, expected):
        self.assertEqual(value, {"provider": expected, "source_sha": HEAD})

    def test_labels_and_reruns_cannot_change_openrouter_route(self):
        self.assert_provider(select([pull()], attempt=1), "openrouter")
        self.assert_provider(select([pull()], attempt=2), "openrouter")
        self.assert_provider(select([pull()], attempt=3), "openrouter")
        self.assert_provider(select([pull(labels=[])]), "openrouter")
        self.assert_provider(select([pull(labels=[{"name": "ci:openai-other"}])]), "openrouter")
        self.assert_provider(select([]), "openrouter")  # Fork metadata is intentionally not fetched.

    def test_forks_deleted_repositories_and_dependabot_keep_openrouter_route(self):
        fork = pull()
        fork["head"]["repo"]["full_name"] = "contributor/notte"
        deleted = pull()
        deleted["head"]["repo"] = None
        foreign_base = pull()
        foreign_base["base"]["repo"]["full_name"] = "other/notte"
        for pr in (fork, deleted, foreign_base, pull(user={"login": "dependabot[bot]"})):
            with self.subTest(pr=pr):
                self.assert_provider(select([pr]), "openrouter")

    def test_stale_closed_wrong_base_and_ambiguous_prs_fail_closed(self):
        wrong_head = pull()
        wrong_head["head"]["sha"] = OTHER
        wrong_base = pull()
        wrong_base["base"]["ref"] = "release"
        for prs in ([wrong_head], [wrong_base], [pull(state="closed")], [pull(), pull()]):
            with self.subTest(prs=prs), self.assertRaises(ValueError):
                select(prs)

    def test_main_requires_exact_actual_merged_same_repository_commit(self):
        merged = pull(state="closed", merged=True, merge_commit_sha=HEAD)
        self.assert_provider(select([merged], event="push", ref="refs/heads/main", attempt=1), "openrouter")
        # Squash changes the commit SHA; the old PR head is not the main commit.
        merged["head"]["sha"] = OTHER
        self.assert_provider(select([merged], event="push", ref="refs/heads/main"), "openrouter")
        for pr in (
            pull(state="closed", merged=True, merge_commit_sha=OTHER),
            pull(state="closed", merged=False, merge_commit_sha=HEAD),
            pull(state="open", merged=True, merge_commit_sha=HEAD),
            pull(state="closed", merged=True, merge_commit_sha=HEAD, labels=[]),
            pull(state="closed", merged=True, merge_commit_sha=HEAD, user={"login": "dependabot[bot]"}),
        ):
            with self.subTest(pr=pr):
                self.assert_provider(select([pr], event="push", ref="refs/heads/main"), "openrouter")
        foreign = copy.deepcopy(merged)
        foreign["head"]["repo"]["full_name"] = "other/notte"
        wrong_base = copy.deepcopy(merged)
        wrong_base["base"]["ref"] = "release"
        for pr in (foreign, wrong_base):
            self.assert_provider(select([pr], event="push", ref="refs/heads/main"), "openrouter")

    def test_main_ignores_irrelevant_associations_but_refuses_multiple_matches(self):
        merged = pull(state="closed", merged=True, merge_commit_sha=HEAD)
        self.assert_provider(select([], event="push", ref="refs/heads/main"), "openrouter")
        self.assert_provider(select([pull(), merged], event="push", ref="refs/heads/main"), "openrouter")
        with self.assertRaises(ValueError):
            select([merged, merged], event="push", ref="refs/heads/main")

    def test_other_events_or_refs_cannot_authorize_paid_provider(self):
        for event, ref in (
            ("push", "refs/heads/ci-reviewed/openai/1214"),
            ("push", "refs/heads/feature"),
            ("workflow_dispatch", "refs/heads/main"),
            ("schedule", "refs/heads/main"),
            ("pull_request_target", "refs/heads/main"),
        ):
            with self.subTest(event=event, ref=ref):
                self.assert_provider(select([pull()], event=event, ref=ref), "openrouter")

    def test_malformed_metadata_and_workflow_identity_fail_closed(self):
        malformed_branch = pull()
        malformed_branch["head"]["sha"] = 1
        missing_repository = pull()
        del missing_repository["head"]["repo"]
        for prs in (
            {},
            [None],
            [pull(labels="ci:openai")],
            [pull(labels=[{}])],
            [pull(user={})],
            [pull(user={"login": ""})],
            [pull(state=[])],
            [malformed_branch],
            [missing_repository],
        ):
            with self.subTest(prs=prs), self.assertRaises(ValueError):
                select(prs)
        for pr in (
            pull(merged="true"),
            pull(merged=True, merge_commit_sha="not-a-sha"),
            pull(merged=True, merge_commit_sha=int("1" * 40)),
        ):
            with self.subTest(pr=pr), self.assertRaises(ValueError):
                select([pr], event="push", ref="refs/heads/main")
        for kwargs in ({"head": "invalid"}, {"attempt": 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                select([pull()], **kwargs)

    def test_real_cli_prints_only_provider_and_exact_head(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.json"
            for prs, provider in (([pull()], "openrouter"), ([], "openrouter")):
                path.write_text(json.dumps(prs), encoding="utf-8")
                result = self.cli(path)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), {"provider": provider, "source_sha": HEAD})
                self.assertEqual(result.stderr, "")
            for raw in (
                "not-json-with-sensitive-fixture",
                json.dumps([{"sensitive": "fixture"}]),
                json.dumps([pull(), pull()]),
            ):
                path.write_text(raw, encoding="utf-8")
                result = self.cli(path)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, "Invalid CI provider metadata\n")
            self.assertEqual(self.cli(Path(directory) / "absent").stderr, "Invalid CI provider metadata\n")

    @staticmethod
    def cli(path):
        return subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/ci_provider.py"),
                "--event",
                "pull_request",
                "--ref",
                "refs/pull/1214/merge",
                "--repository",
                REPOSITORY,
                "--head",
                HEAD,
                "--attempt",
                "2",
                "--pulls",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )


if __name__ == "__main__":
    unittest.main()
