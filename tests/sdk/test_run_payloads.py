import base64
import hashlib
import json
from unittest.mock import MagicMock, patch

import pytest
from notte_sdk import NotteClient
from notte_sdk.endpoints.run_payloads import UploadReference, UploadResponse, offload_run_fields, resolve_run_fields


def reference(raw):
    return UploadReference(
        upload_id="upload", size_bytes=len(raw), sha256=base64.b64encode(hashlib.sha256(raw).digest()).decode()
    )


def storage_session(response):
    session = MagicMock()
    session.__enter__.return_value = session
    response.__enter__.return_value = response
    session.put.return_value = response
    session.get.return_value = response
    return session


def test_small_update_remains_inline_and_preserves_unset_fields():
    client = NotteClient(api_key="test")
    with (
        patch.object(client.functions, "request") as request,
        patch("notte_sdk.endpoints.run_payloads.requests.Session") as s3,
    ):
        client.functions.update_run("fn", "run", status="closed", result="ok")
    body = request.call_args.args[0].request.model_dump()
    assert body == {"status": "closed", "result": "ok"}
    s3.assert_not_called()


def test_large_logs_are_uploaded_before_final_update_without_api_credentials():
    client = NotteClient(api_key="test-secret")
    logs = ["some log"] * 100
    original = {"status": "closed", "logs": logs}
    raw = json.dumps(logs, ensure_ascii=False).encode()
    upload = UploadResponse(reference=reference(raw), url="https://storage/object", headers={"If-None-Match": "*"})
    response = MagicMock(status_code=200)
    session = storage_session(response)
    uploaded = []
    session.put.side_effect = lambda *args, **kwargs: (uploaded.append(kwargs["data"].read()), response)[1]
    with (
        patch("notte_sdk.endpoints.run_payloads.INLINE_FIELD_BYTES", 10),
        patch.object(client.functions, "request", return_value=upload) as request,
        patch("notte_sdk.endpoints.run_payloads.requests.Session", return_value=session),
    ):
        body = offload_run_fields(client.functions, "fn/runs/run", original)
    assert uploaded == [raw]
    assert "logs" not in body
    assert body["payloads"]["logs"] == upload.reference.model_dump()
    assert original["logs"] is logs
    assert request.call_args.args[0].path == "fn/runs/run/payloads/logs/upload"
    assert session.put.call_args.kwargs["headers"] == {"If-None-Match": "*"}
    assert session.put.call_args.kwargs["allow_redirects"] is False


def test_upload_failure_never_finalizes_run():
    client = NotteClient(api_key="test")
    raw = json.dumps("long result").encode()
    upload = UploadResponse(reference=reference(raw), url="https://storage/object", headers={})
    response = MagicMock(status_code=503)
    response.raise_for_status.side_effect = RuntimeError("upload unavailable")
    with (
        patch("notte_sdk.endpoints.run_payloads.INLINE_FIELD_BYTES", 1),
        patch.object(client.functions, "request", return_value=upload) as request,
        patch("notte_sdk.endpoints.run_payloads.requests.Session", return_value=storage_session(response)),
    ):
        with pytest.raises(RuntimeError, match="upload unavailable"):
            client.functions.update_run("fn", "run", status="closed", result="long result")
    assert request.call_count == 1
    assert request.call_args.args[0].method == "POST"


@pytest.mark.parametrize("failure", [None, "checksum", "truncated", "oversized"])
def test_download_verifies_all_bytes_before_decoding(failure):
    raw = json.dumps(["one", "two"]).encode()
    ref = reference(raw)
    delivered = raw
    if failure == "checksum":
        delivered = raw.replace(b"one", b"bad")
    if failure == "truncated":
        delivered = raw[:-1]
    if failure == "oversized":
        delivered = raw + b" "
    response = MagicMock(status_code=200)
    response.iter_content.return_value = [delivered[:4], delivered[4:]]
    session = storage_session(response)
    data = {
        "status": "closed",
        "logs": [],
        "payloads": {"logs": ref.model_dump()},
        "payload_urls": {"logs": "https://storage/object"},
    }
    with patch("notte_sdk.endpoints.run_payloads.requests.Session", return_value=session):
        if failure:
            with pytest.raises(ValueError):
                resolve_run_fields(data)
        else:
            assert resolve_run_fields(data) == {"status": "closed", "logs": ["one", "two"]}
    assert "headers" not in session.get.call_args.kwargs
    assert session.get.call_args.kwargs["stream"] is True


@pytest.mark.parametrize("urls", [{}, {"logs": ""}, {"logs": None}])
def test_missing_download_url_fails_before_storage_request(urls):
    data = {"payloads": {"logs": reference(b"[]").model_dump()}, "payload_urls": urls}
    with patch("notte_sdk.endpoints.run_payloads.requests.Session") as storage:
        with pytest.raises(ValueError, match="Missing download URL.*logs"):
            resolve_run_fields(data)
    storage.assert_not_called()


def test_result_preview_is_bounded_and_full_result_is_in_storage():
    result = "x" * 20000
    raw = json.dumps(result).encode()
    client = MagicMock()
    client.request.return_value = UploadResponse(reference=reference(raw), url="https://storage/object", headers={})
    with (
        patch("notte_sdk.endpoints.run_payloads.INLINE_FIELD_BYTES", 1),
        patch(
            "notte_sdk.endpoints.run_payloads.requests.Session",
            return_value=storage_session(MagicMock(status_code=200)),
        ),
    ):
        body = offload_run_fields(client, "fn/runs/run", {"status": "closed", "result": result})
    assert len(body["result_preview"]) == 16000
    assert "result" not in body
    assert body["payloads"]["result"]["size_bytes"] == len(raw)
