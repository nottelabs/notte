"""Transfer large run fields directly to object storage, outside API requests.

`offload_run_fields` and `resolve_run_fields` have async twins for `AsyncNotteClient`, which run
the same steps below and do every local file read and write in a worker thread.
"""

import asyncio
import base64
import hashlib
import json
from tempfile import TemporaryFile
from typing import IO, Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, RootModel

from notte_sdk._compat.run_payloads import UploadReference
from notte_sdk._compat.run_payloads import UploadResponse as UploadResponse
from notte_sdk._generated.resources import AsyncRunPayloadsOperations, RunPayloadsOperations
from notte_sdk._transport import aget_object, aput_object, get_object, put_object

INLINE_FIELD_BYTES = 1024 * 1024
MAX_PAYLOAD_BYTES = 256 * 1024 * 1024
PAYLOAD_FIELDS = ("result", "logs", "variables")
# Object storage (connect, read) timeouts and the read size of downloads.
_STORAGE_TIMEOUT = (30, 300)
_CHUNK_SIZE = 64 * 1024


class PayloadMode(BaseModel):
    payload_mode: Literal["references"] = "references"


class RunUpdateBody(RootModel[dict[str, Any]]):
    pass


def _storage_url(url: str) -> str:
    # Never forward API credentials to an object URL, or follow its redirects.
    if urlsplit(url).scheme != "https":
        raise ValueError("Run payload storage requires an HTTPS URL")
    return url


def _wire_fields(fields: dict[str, Any]) -> dict[str, Any]:
    data = dict(fields)
    # The persisted result column and read contract are text, even when a
    # caller supplies a structured result to update_run.
    if data.get("result") is not None and not isinstance(data["result"], str):
        data["result"] = json.dumps(data["result"], ensure_ascii=False, allow_nan=False)
    return data


def _spool(field: str, value: Any) -> tuple[IO[bytes], int, str] | None:
    """Encode a field as JSON into a temporary file: the file (at its start), its size and SHA-256.

    `None` when the field is small enough to stay inline. The caller closes the file.
    """
    payload = TemporaryFile(mode="w+b")
    try:
        # JSON mode matches the wire representation of normal SDK requests.
        for fragment in json.JSONEncoder(ensure_ascii=False, allow_nan=False).iterencode(value):
            _ = payload.write(fragment.encode("utf-8"))
            if payload.tell() > MAX_PAYLOAD_BYTES:
                raise ValueError(f"Function run {field} exceeds the {MAX_PAYLOAD_BYTES}-byte payload limit")
        size = payload.tell()
        if size <= INLINE_FIELD_BYTES:
            payload.close()
            return None
        _ = payload.seek(0)
        digest = hashlib.sha256()
        while chunk := payload.read(_CHUNK_SIZE):
            digest.update(chunk)
        _ = payload.seek(0)
        return payload, size, base64.b64encode(digest.digest()).decode("ascii")
    except BaseException:
        payload.close()
        raise


def _upload_url(upload: UploadResponse, size: int, checksum: str) -> str:
    if upload.reference.size_bytes != size or upload.reference.sha256 != checksum:
        raise ValueError("Run payload upload reference does not match the local payload")
    return _storage_url(upload.url)


def _check_uploaded(status: int) -> None:
    if not 200 <= status < 300:
        raise ValueError("Run payload upload did not complete")


def _replace_with_reference(
    data: dict[str, Any], references: dict[str, dict[str, Any]], field: str, upload: UploadResponse
) -> None:
    references[field] = upload.reference.model_dump()
    if field == "result" and isinstance(data[field], str):
        data["result_preview"] = data[field][:16000]
    del data[field]


def _with_references(data: dict[str, Any], references: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if references:
        data["payloads"] = references
    return data


def offload_run_fields(
    client: RunPayloadsOperations, function_id: str, run_id: str, fields: dict[str, Any]
) -> dict[str, Any]:
    """Spool JSON to disk; send only small values and verified references to API."""
    data = _wire_fields(fields)
    references: dict[str, dict[str, Any]] = {}
    for field in PAYLOAD_FIELDS:
        if field not in data or data[field] is None:
            continue
        spooled = _spool(field, data[field])
        if spooled is None:
            continue
        payload, size, checksum = spooled
        with payload:
            upload = client.prepare_run_payload_upload(function_id, run_id, field, size_bytes=size, sha256=checksum)
            url = _upload_url(upload, size, checksum)
            # The storage request never carries the API token, preview selector or capability headers.
            _check_uploaded(put_object(url, payload, headers=upload.headers, timeout=_STORAGE_TIMEOUT))
        _replace_with_reference(data, references, field, upload)
    return _with_references(data, references)


async def aoffload_run_fields(
    client: AsyncRunPayloadsOperations, function_id: str, run_id: str, fields: dict[str, Any]
) -> dict[str, Any]:
    """The async twin of `offload_run_fields`: encoding and file I/O run in worker threads."""
    data = await asyncio.to_thread(_wire_fields, fields)
    references: dict[str, dict[str, Any]] = {}
    for field in PAYLOAD_FIELDS:
        if field not in data or data[field] is None:
            continue
        spooled = await asyncio.to_thread(_spool, field, data[field])
        if spooled is None:
            continue
        payload, size, checksum = spooled
        try:
            upload = await client.prepare_run_payload_upload(
                function_id, run_id, field, size_bytes=size, sha256=checksum
            )
            url = _upload_url(upload, size, checksum)
            _check_uploaded(await aput_object(url, payload, headers=upload.headers, timeout=_STORAGE_TIMEOUT))
        finally:
            await asyncio.to_thread(payload.close)
        _replace_with_reference(data, references, field, upload)
    return _with_references(data, references)


def _download_reference(field: str, raw_reference: Any, urls: dict[str, Any]) -> tuple[UploadReference, str]:
    """A payload reference and its storage URL, validated before any request."""
    if field not in PAYLOAD_FIELDS:
        raise ValueError(f"Unknown function run payload field: {field}")
    reference = UploadReference.model_validate(raw_reference)
    if not 0 < reference.size_bytes <= MAX_PAYLOAD_BYTES:
        raise ValueError("Invalid function run payload size")
    url = urls.get(field)
    if not url:
        raise ValueError(f"Missing download URL for function run payload field: {field}")
    return reference, _storage_url(url)


class _PayloadDownload:
    """A payload's bytes, spooled to a temporary file and checked against its reference before decoding."""

    def __init__(self, reference: UploadReference) -> None:
        self._reference: UploadReference = reference
        self._file: IO[bytes] = TemporaryFile(mode="w+b")
        self._digest: Any = hashlib.sha256()

    @staticmethod
    def check_status(status: int) -> None:
        if status != 200:
            raise ValueError("Run payload download did not complete")

    def write(self, chunk: bytes) -> None:
        if self._file.tell() + len(chunk) > self._reference.size_bytes:
            raise ValueError("Run payload download exceeds its declared size")
        _ = self._file.write(chunk)
        self._digest.update(chunk)

    def load(self) -> Any:
        checksum = base64.b64encode(self._digest.digest()).decode()
        if self._file.tell() != self._reference.size_bytes or checksum != self._reference.sha256:
            raise ValueError("Run payload download failed size/checksum verification")
        _ = self._file.seek(0)
        return json.load(self._file)

    def close(self) -> None:
        self._file.close()


def resolve_run_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Hydrate on the caller's machine, checking the bytes before decoding JSON."""
    data = dict(data)
    references = data.pop("payloads", {})
    urls = data.pop("payload_urls", {})
    for field, raw_reference in references.items():
        reference, url = _download_reference(field, raw_reference, urls)
        payload = _PayloadDownload(reference)
        try:
            with get_object(url, timeout=_STORAGE_TIMEOUT, chunk_size=_CHUNK_SIZE) as (status, chunks):
                payload.check_status(status)
                for chunk in chunks:
                    payload.write(chunk)
            data[field] = payload.load()
        finally:
            payload.close()
    return data


async def aresolve_run_fields(data: dict[str, Any]) -> dict[str, Any]:
    """The async twin of `resolve_run_fields`: file writes, checks and decoding run in worker threads."""
    data = dict(data)
    references = data.pop("payloads", {})
    urls = data.pop("payload_urls", {})
    for field, raw_reference in references.items():
        reference, url = _download_reference(field, raw_reference, urls)
        payload = await asyncio.to_thread(_PayloadDownload, reference)
        try:
            async with aget_object(url, timeout=_STORAGE_TIMEOUT, chunk_size=_CHUNK_SIZE) as (status, chunks):
                payload.check_status(status)
                async for chunk in chunks:
                    await asyncio.to_thread(payload.write, chunk)
            data[field] = await asyncio.to_thread(payload.load)
        finally:
            await asyncio.to_thread(payload.close)
    return data
