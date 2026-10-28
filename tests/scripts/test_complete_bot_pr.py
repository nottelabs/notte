"""Bot completion authorization and head races, with no GitHub writes."""

import copy
import io
import json
import subprocess
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from scripts import complete_bot_pr as bot

HEAD = "a" * 40
OTHER = "b" * 40
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def fixture():
    pr = {
        "number": 42,
        "state": "open",
        "draft": False,
        "body": "<!-- bot-pr-run: 123 -->",
        "user": {"login": bot.BOT},
        "head": {"sha": HEAD, "ref": "chore/bump-submodules", "repo": {"full_name": bot.REPOSITORY}},
        "base": {"ref": "main", "repo": {"full_name": bot.REPOSITORY}},
    }
    run = {
        "repository": {"full_name": bot.REPOSITORY},
        "head_repository": {"full_name": bot.REPOSITORY},
        "head_branch": "main",
        "head_sha": OTHER,
        "event": "schedule",
        "path": bot.PRODUCERS[pr["head"]["ref"]],
        "status": "completed",
        "conclusion": "success",
    }
    manifest = {
        "GITHUB_REPOSITORY": bot.REPOSITORY,
        "GITHUB_RUN_ID": "123",
        "BRANCH": pr["head"]["ref"],
        "PR_NUMBER": "42",
        "HEAD_SHA": HEAD,
    }
    return pr, run, manifest


def archive(manifest):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as zipped:
        zipped.writestr("bot-pr.json", json.dumps(manifest))
    return data.getvalue()


def attest(fixture, *, comparison="ahead", artifacts=None):
    pr, run, manifest = fixture
    if artifacts is None:
        artifacts = [{"id": 1, "name": "bot-pr", "expired": False, "size_in_bytes": 512}]
    with (
        patch.object(bot, "api", side_effect=[run, {"status": comparison}, {"artifacts": artifacts}]),
        patch.object(bot, "gh", return_value=archive(manifest)),
    ):
        return bot.attested(pr)


@pytest.mark.parametrize("branch", bot.PRODUCERS)
@pytest.mark.parametrize("event", ["schedule", "workflow_dispatch"])
def test_exact_trusted_producer_head_is_owned(fixture, branch, event):
    pr, run, manifest = fixture
    pr["head"]["ref"] = manifest["BRANCH"] = branch
    run.update(path=bot.PRODUCERS[branch], event=event)
    assert bot.owned(pr)
    assert attest(fixture)


@pytest.mark.parametrize(
    "field,value",
    [("state", "closed"), ("draft", True), ("user", {"login": "attacker"})],
)
def test_closed_draft_or_other_author_cannot_merge(fixture, field, value):
    pr = fixture[0]
    pr[field] = value
    assert not bot.owned(pr)


@pytest.mark.parametrize(
    "part,field,value",
    [
        ("head", "repo", {"full_name": "attacker/notte"}),
        ("head", "repo", None),
        ("head", "sha", "invalid"),
        ("head", "ref", "feature"),
        ("base", "repo", {"full_name": "attacker/notte"}),
        ("base", "ref", "prod"),
    ],
)
def test_fork_branch_and_repository_impersonation_fail_closed(fixture, part, field, value):
    pr = fixture[0]
    pr[part][field] = value
    assert not bot.owned(pr)


@pytest.mark.parametrize(
    "field,value",
    [
        ("event", "pull_request"),
        ("event", "workflow_run"),
        ("head_branch", "feature"),
        ("repository", {"full_name": "attacker/notte"}),
        ("head_repository", {"full_name": "attacker/notte"}),
        ("path", ".github/workflows/other.yml"),
        ("conclusion", "failure"),
        ("status", "in_progress"),
    ],
)
def test_untrusted_failed_and_incomplete_producer_events_do_not_authorize(fixture, field, value):
    fixture[1][field] = value
    assert not attest(fixture)


@pytest.mark.parametrize("comparison", ["behind", "diverged"])
def test_producer_must_be_in_trusted_main_history(fixture, comparison):
    assert not attest(fixture, comparison=comparison)


@pytest.mark.parametrize("field", ["GITHUB_REPOSITORY", "GITHUB_RUN_ID", "BRANCH", "PR_NUMBER", "HEAD_SHA"])
def test_attestation_cannot_authorize_a_different_pr_or_stale_head(fixture, field):
    fixture[2][field] = "different"
    assert not attest(fixture)


@pytest.mark.parametrize("body", [None, "", "<!-- bot-pr-run: 123 -->\n<!-- bot-pr-run: 456 -->"])
def test_missing_or_ambiguous_producer_identity_is_rejected(fixture, body):
    fixture[0]["body"] = body
    with patch.object(bot, "api") as api:
        assert not bot.attested(fixture[0])
        api.assert_not_called()


def test_artifact_must_be_unique_live_and_bounded(fixture):
    item = {"id": 1, "name": "bot-pr", "expired": False, "size_in_bytes": 512}
    for artifacts in ([], [item, item], [{**item, "expired": True}], [{**item, "size_in_bytes": 4097}]):
        assert not attest(fixture, artifacts=artifacts)


def test_approval_must_be_current_and_not_blocked_or_dismissed(fixture):
    approved = {"user": {"login": "reviewer"}, "state": "APPROVED", "commit_id": HEAD}
    blocked = {**approved, "user": {"login": "other"}, "state": "CHANGES_REQUESTED"}
    for reviews, expected in (
        ([], False),
        ([approved], True),
        ([{**approved, "commit_id": OTHER}], False),
        ([approved, blocked], False),
        ([approved, {**approved, "state": "DISMISSED"}], False),
        ([blocked, {**blocked, "state": "APPROVED"}], True),
    ):
        with patch.object(bot, "gh", return_value=json.dumps([reviews]).encode()):
            assert bot.reviewed(fixture[0]) is expected


@pytest.mark.parametrize("status", [1, 8])
def test_failed_or_pending_checks_never_merge(fixture, status):
    with patch.object(bot.subprocess, "run", return_value=subprocess.CompletedProcess([], status, b"[]")):
        assert not bot.checks_passed(fixture[0])


@pytest.mark.parametrize(
    "checks", [[], [{"name": "tests", "bucket": "skipping"}], [{"name": "other", "bucket": "pass"}]]
)
def test_required_tests_gate_must_be_present_and_pass(fixture, checks):
    with patch.object(
        bot.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, json.dumps(checks).encode())
    ):
        assert not bot.checks_passed(fixture[0])


def test_checks_include_all_reported_and_all_required_checks(fixture):
    passed = subprocess.CompletedProcess([], 0, b'[{"name":"tests","bucket":"pass"}]')
    with patch.object(bot.subprocess, "run", return_value=passed) as run:
        assert bot.checks_passed(fixture[0])
        assert len(run.call_args_list) == 2
        assert "--required" not in run.call_args_list[0].args[0]
        assert "--required" in run.call_args_list[1].args[0]
    with patch.object(bot.subprocess, "run", return_value=subprocess.CompletedProcess([], 4, b"")):
        with pytest.raises(RuntimeError):
            bot.checks_passed(fixture[0])


@pytest.mark.parametrize("changed", [False, True])
def test_merge_revalidates_current_head_and_uses_atomic_sha_guard(fixture, changed):
    pr = fixture[0]
    current = copy.deepcopy(pr)
    if changed:
        current["head"]["sha"] = OTHER
    with (
        patch.object(bot, "api", side_effect=[pr, current]),
        patch.object(bot, "attested", return_value=True),
        patch.object(bot, "reviewed", return_value=True),
        patch.object(bot, "checks_passed", return_value=True),
        patch.object(
            bot,
            "gh",
            return_value=json.dumps(
                {"headRefOid": HEAD, "mergeStateStatus": "CLEAN", "reviewDecision": "APPROVED"}
            ).encode(),
        ) as gh,
    ):
        assert bot.complete(42) is not changed
        if changed:
            gh.assert_not_called()
        else:
            args = gh.call_args.args
            assert args[:3] == ("pr", "merge", "42")
            assert args[args.index("--match-head-commit") + 1] == HEAD
            assert "--delete-branch" not in args
            assert "--admin" not in args


def test_workflows_use_trusted_default_branch_and_no_waiting_runner():
    workflow = yaml.safe_load((ROOT / ".github/workflows/complete-bot-pr.yml").read_text())
    assert set(workflow[True]) == {"workflow_run", "check_run", "status", "schedule"}
    assert set(workflow["permissions"].values()) == {"read"}
    assert "github.event.workflow_run.name != 'complete-bot-pr'" in workflow["jobs"]["complete"]["if"]
    checkout = workflow["jobs"]["complete"]["steps"][0]
    assert checkout["with"] == {"ref": "${{ github.workflow_sha }}", "persist-credentials": False}
    for producer in bot.PRODUCERS.values():
        text = (ROOT / producer).read_text()
        config = yaml.safe_load(text)
        assert config["permissions"] == {"contents": "read"}
        assert "gh pr checks" not in text and "sleep 30" not in text
        assert "gh pr merge" not in text
        assert "--body-file" in text
        assert "HEAD_SHA" in text and "bot-pr.json" in text
        assert "github.ref == 'refs/heads/main'" in text


@pytest.mark.parametrize(
    "field,value",
    [
        ("headRefOid", OTHER),
        ("mergeStateStatus", "BEHIND"),
        ("mergeStateStatus", "BLOCKED"),
        ("mergeStateStatus", "DIRTY"),
        ("reviewDecision", "REVIEW_REQUIRED"),
    ],
)
def test_server_freshness_review_and_conversation_rules_are_not_bypassed(fixture, field, value):
    pr = fixture[0]
    state = {"headRefOid": HEAD, "mergeStateStatus": "CLEAN", "reviewDecision": "APPROVED", field: value}
    with (
        patch.object(bot, "api", return_value=pr),
        patch.object(bot, "attested", return_value=True),
        patch.object(bot, "reviewed", return_value=True),
        patch.object(bot, "checks_passed", return_value=True),
        patch.object(bot, "gh", return_value=json.dumps(state).encode()) as gh,
    ):
        assert not bot.complete(42)
        assert all(call.args[1] != "merge" for call in gh.call_args_list)
