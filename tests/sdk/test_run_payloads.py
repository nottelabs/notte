import base64
import hashlib
import json
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import httpx
import pytest
import requests
from notte_sdk import NotteClient
from notte_sdk.endpoints.run_payloads import UploadReference, UploadResponse, offload_run_fields, resolve_run_fields
from notte_sdk.errors import NotteHTTPStatusError


def reference(raw):
    return UploadReference(
        upload_id="upload", size_bytes=len(raw), sha256=base64.b64encode(hashlib.sha256(raw).digest()).decode()
    )


class _Chunks(httpx.SyncByteStream):
    def __init__(self, storage: "Storage") -> None:
        self.storage = storage

    def __iter__(self) -> Iterator[bytes]:
        for chunk in self.storage.chunks:
            self.storage.consumed.append(chunk)
            yield chunk


class Storage:
    """Object storage behind the transport's storage client, recording every request."""

    def __init__(self, status: int = 200, chunks: tuple[bytes, ...] = (), headers: dict[str, str] | None = None):
        self.status = status
        self.chunks = list(chunks)
        self.headers = headers or {}
        self.consumed: list[bytes] = []
        self.requests: list[httpx.Request] = []

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status, headers=self.headers, stream=_Chunks(self))

    def client(self) -> httpx.Client:
        # The SDK's own client follows redirects by default, so this one does too.
        return httpx.Client(transport=httpx.MockTransport(self._handle), follow_redirects=True)

    def patch(self):
        return patch("notte_sdk._transport.http_client", side_effect=self.client)

    @property
    def uploads(self) -> list[bytes]:
        return [request.content for request in self.requests if request.method == "PUT"]


def sent_headers(request: httpx.Request) -> dict[str, str]:
    """Headers set by the SDK, without those httpx adds to every request."""
    added = {"host", "accept", "accept-encoding", "connection", "user-agent", "content-length"}
    return {name: value for name, value in request.headers.items() if name not in added}


def test_small_update_remains_inline_and_preserves_unset_fields():
    client = NotteClient(api_key="test")
    with (
        patch.object(client.functions, "request") as request,
        Storage().patch() as s3,
    ):
        client.functions.run_update_metadata("fn", "run", status="closed", result="ok")
    body = request.call_args.args[0].request.model_dump()
    assert body == {"status": "closed", "result": "ok"}
    s3.assert_not_called()


def test_large_logs_are_uploaded_before_final_update_without_api_credentials():
    client = NotteClient(api_key="test-secret")
    logs = ["some log"] * 100
    original = {"status": "closed", "logs": logs}
    raw = json.dumps(logs, ensure_ascii=False).encode()
    upload = UploadResponse(reference=reference(raw), url="https://storage/object", headers={"If-None-Match": "*"})
    storage = Storage()
    with (
        patch("notte_sdk.endpoints.run_payloads.INLINE_FIELD_BYTES", 10),
        patch.object(client.functions, "request", return_value=upload) as request,
        storage.patch(),
    ):
        body = offload_run_fields(client.functions, "fn", "run", original)
    assert storage.uploads == [raw]
    assert "logs" not in body
    assert body["payloads"]["logs"] == upload.reference.model_dump()
    assert original["logs"] is logs
    assert request.call_args.args[0].path == "/functions/fn/runs/run/payloads/logs/upload"
    put = storage.requests[0]
    assert (put.method, str(put.url)) == ("PUT", "https://storage/object")
    assert sent_headers(put) == {"if-none-match": "*"}
    assert put.headers["content-length"] == str(len(raw))


@pytest.mark.parametrize("method", ["PUT", "GET"])
def test_storage_redirects_are_not_followed(method):
    raw = json.dumps("long result").encode()
    storage = Storage(status=307, headers={"location": "https://elsewhere/object"})
    with storage.patch(), pytest.raises(ValueError, match="did not complete"):
        if method == "PUT":
            upload = UploadResponse(reference=reference(raw), url="https://storage/object", headers={})
            client = NotteClient(api_key="test").functions
            with (
                patch("notte_sdk.endpoints.run_payloads.INLINE_FIELD_BYTES", 1),
                patch.object(client, "request", return_value=upload),
            ):
                _ = offload_run_fields(client, "fn", "run", {"result": "long result"})
        else:
            data = {
                "payloads": {"logs": reference(raw).model_dump()},
                "payload_urls": {"logs": "https://storage/object"},
            }
            _ = resolve_run_fields(data)
    assert [(request.method, str(request.url)) for request in storage.requests] == [(method, "https://storage/object")]


def test_upload_failure_never_finalizes_run():
    client = NotteClient(api_key="test")
    raw = json.dumps("long result").encode()
    upload = UploadResponse(reference=reference(raw), url="https://storage/object", headers={})
    with (
        patch("notte_sdk.endpoints.run_payloads.INLINE_FIELD_BYTES", 1),
        patch.object(client.functions, "request", return_value=upload) as request,
        Storage(status=503).patch(),
    ):
        with pytest.raises(NotteHTTPStatusError, match="503 Server Error") as error:
            client.functions.run_update_metadata("fn", "run", status="closed", result="long result")
    # Callers catching the requests exception still catch it.
    assert isinstance(error.value, requests.HTTPError)
    assert error.value.response.status_code == 503
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
    storage = Storage(chunks=(delivered[:4], delivered[4:]))
    data = {
        "status": "closed",
        "logs": [],
        "payloads": {"logs": ref.model_dump()},
        "payload_urls": {"logs": "https://storage/object"},
    }
    with storage.patch():
        if failure:
            with pytest.raises(ValueError):
                resolve_run_fields(data)
        else:
            assert resolve_run_fields(data) == {"status": "closed", "logs": ["one", "two"]}
    assert [(request.method, str(request.url)) for request in storage.requests] == [("GET", "https://storage/object")]
    assert sent_headers(storage.requests[0]) == {}


def test_download_stops_reading_past_the_declared_size():
    raw = json.dumps(["one", "two"]).encode()
    # Larger than the 64 KiB read size, so the first read already exceeds the declared size.
    extra = b" " * (64 * 1024)
    storage = Storage(chunks=(raw, extra, b"never read"))
    data = {"payloads": {"logs": reference(raw).model_dump()}, "payload_urls": {"logs": "https://storage/object"}}
    with storage.patch(), pytest.raises(ValueError, match="exceeds its declared size"):
        _ = resolve_run_fields(data)
    # The body is streamed: nothing after the oversized read is fetched.
    assert storage.consumed == [raw, extra]


@pytest.mark.parametrize("urls", [{}, {"logs": ""}, {"logs": None}])
def test_missing_download_url_fails_before_storage_request(urls):
    data = {"payloads": {"logs": reference(b"[]").model_dump()}, "payload_urls": urls}
    with Storage().patch() as storage:
        with pytest.raises(ValueError, match="Missing download URL.*logs"):
            resolve_run_fields(data)
    storage.assert_not_called()


def test_result_preview_is_bounded_and_full_result_is_in_storage():
    result = "x" * 20000
    raw = json.dumps(result).encode()
    client = NotteClient(api_key="test").functions
    upload = UploadResponse(reference=reference(raw), url="https://storage/object", headers={})
    with (
        patch.object(client, "request", return_value=upload),
        patch("notte_sdk.endpoints.run_payloads.INLINE_FIELD_BYTES", 1),
        Storage().patch(),
    ):
        body = offload_run_fields(client, "fn", "run", {"status": "closed", "result": result})
    assert len(body["result_preview"]) == 16000
    assert "result" not in body
    assert body["payloads"]["result"]["size_bytes"] == len(raw)


@pytest.mark.parametrize("threshold", [1, 10000])
def test_run_update_serializes_python_values_before_offloading(threshold):
    from datetime import datetime, timezone
    from uuid import UUID

    client = NotteClient(api_key="test").functions
    stamp = datetime(2026, 10, 13, tzinfo=timezone.utc)
    identifier = UUID("f18936c0-6926-4d2c-8a40-9a991c5412bd")
    storage = Storage()

    def respond(endpoint):
        if endpoint.method == "POST":
            return UploadResponse(
                reference=UploadReference(upload_id="upload", **endpoint.request.model_dump()),
                url="https://storage/object",
                headers={},
            )
        return MagicMock()

    with (
        patch("notte_sdk.endpoints.run_payloads.INLINE_FIELD_BYTES", threshold),
        patch.object(client, "request", side_effect=respond) as request,
        storage.patch(),
    ):
        client.run_update_metadata("fn", "run", status="closed", variables={"at": stamp}, result=identifier)
    uploads = storage.uploads
    body = request.call_args.args[0].request.model_dump()
    if threshold == 1:
        assert [json.loads(raw) for raw in uploads] == [str(identifier), {"at": "2026-10-13T00:00:00Z"}]
        assert set(body["payloads"]) == {"variables", "result"}
    else:
        assert body == {"status": "closed", "variables": {"at": "2026-10-13T00:00:00Z"}, "result": str(identifier)}
        assert uploads == []
