"""Only the trusted publisher may complete this commit's contract request."""

import importlib.util
import io
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("ci_schema_status", ROOT / "scripts/ci_schema_status.py")
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)
SHA = "a" * 40
NONCE = "b" * 32


def result(state="success", actor=123, nonce=NONCE, context=ci.CONTEXT):
    return {"state": state, "creator": {"id": actor}, "context": context, "description": f"request {nonce}: passed"}


def execute(statuses):
    github = Mock()
    github.request.side_effect = [None, statuses]
    with patch.object(ci.uuid, "uuid4", return_value=Mock(hex=NONCE)):
        ci.check(github, "example/sdk", SHA, "123")
    return github


def test_trusted_result_matches_exact_request_and_uses_only_public_endpoints():
    github = execute([result()])
    assert github.request.call_args_list[0].args == (
        f"repos/example/sdk/statuses/{SHA}",
        {"state": "pending", "context": ci.CONTEXT, "description": f"request {NONCE}"},
    )
    assert github.request.call_args_list[-1].args == (f"repos/example/sdk/commits/{SHA}/statuses?per_page=100&page=1",)


@pytest.mark.parametrize(
    "status",
    [
        result(actor=41898282),
        result(nonce="c" * 32),
        result(context="other"),
        {**result(), "creator": None},
        {**result(), "description": None},
    ],
)
def test_public_token_cannot_forge_a_result_and_old_requests_do_not_count(status):
    github = Mock()
    github.request.side_effect = [None, [status]]
    with (
        patch.object(ci.uuid, "uuid4", return_value=Mock(hex=NONCE)),
        patch.object(ci.time, "monotonic", side_effect=[0, 1, 2, 1201]),
        patch.object(ci.time, "sleep"),
        pytest.raises(TimeoutError),
    ):
        ci.check(github, "example/sdk", SHA, "123")


@pytest.mark.parametrize("state", ["failure", "error"])
def test_failure_is_required(state):
    with pytest.raises(RuntimeError, match="contract check failed"):
        execute([result(state=state)])


def test_missing_publisher_identity_fails_before_creating_a_request():
    github = Mock()
    with pytest.raises(ValueError, match="SDK_SCHEMA_STATUS_ACTOR_ID"):
        ci.check(github, "example/sdk", SHA, "")
    github.request.assert_not_called()


def test_schema_job_has_no_consumer_secret_or_checkout():
    data = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    job = data["jobs"]["schema"]
    assert job["permissions"]["statuses"] == "write"
    assert job["permissions"].get("id-token", "none") == "none"
    assert "secrets." not in str(job)
    assert "SDK_SCHEMA_REPOSITORY" not in str(job)
    assert all(step.get("with", {}).get("repository", "nottelabs/notte") == "nottelabs/notte" for step in job["steps"])


def test_public_status_reads_reuse_etags_without_spending_unchanged_requests():
    response = io.BytesIO(b"[]")
    response.headers = {"ETag": '"fixture-etag"'}
    not_modified = urllib.error.HTTPError("https://api.github.com/public", 304, "Not Modified", {}, None)
    with patch.object(ci.urllib.request, "urlopen", side_effect=[response, not_modified]) as send:
        github = ci.GitHub("fixture-token")
        assert github.request("public") == []
        assert github.request("public") == []
    assert dict(send.call_args.args[0].header_items())["If-none-match"] == '"fixture-etag"'


def test_overlapping_request_cannot_hide_the_matching_result_on_a_later_page():
    github = Mock()
    github.request.side_effect = [None, [result(nonce="c" * 32)] * 100, [result()]]
    with patch.object(ci.uuid, "uuid4", return_value=Mock(hex=NONCE)):
        ci.check(github, "example/sdk", SHA, "123")
    assert [call.args[0] for call in github.request.call_args_list[1:]] == [
        f"repos/example/sdk/commits/{SHA}/statuses?per_page=100&page=1",
        f"repos/example/sdk/commits/{SHA}/statuses?per_page=100&page=2",
    ]


def test_newest_matching_failure_is_not_overridden_by_an_older_success():
    with pytest.raises(RuntimeError, match="contract check failed"):
        execute([result(state="failure"), result()])
