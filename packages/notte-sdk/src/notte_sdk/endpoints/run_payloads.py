"""Transfer large run fields directly to object storage, outside API requests."""

import base64
import hashlib
import json
from tempfile import TemporaryFile
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, RootModel

from notte_sdk._compat.run_payloads import UploadReference
from notte_sdk._compat.run_payloads import UploadResponse as UploadResponse
from notte_sdk._generated.resources import RunPayloadsOperations
from notte_sdk._transport import get_object, put_object

INLINE_FIELD_BYTES = 1024 * 1024
MAX_PAYLOAD_BYTES = 256 * 1024 * 1024
PAYLOAD_FIELDS = ("result", "logs", "variables")


class PayloadMode(BaseModel):
    payload_mode: Literal["references"] = "references"


class RunUpdateBody(RootModel[dict[str, Any]]):
    pass


def _storage_url(url: str) -> str:
    # Never forward API credentials to an object URL, or follow its redirects.
    if urlsplit(url).scheme != "https":
        raise ValueError("Run payload storage requires an HTTPS URL")
    return url


def offload_run_fields(
    client: RunPayloadsOperations, function_id: str, run_id: str, fields: dict[str, Any]
) -> dict[str, Any]:
    """Spool JSON to disk; send only small values and verified references to API."""
    data = dict(fields)
    references: dict[str, dict[str, Any]] = {}
    # The persisted result column and read contract are text, even when a
    # caller supplies a structured result to update_run.
    if data.get("result") is not None and not isinstance(data["result"], str):
        data["result"] = json.dumps(data["result"], ensure_ascii=False, allow_nan=False)
    for field in PAYLOAD_FIELDS:
        if field not in data or data[field] is None:
            continue
        # JSON mode matches the wire representation of normal SDK requests.
        with TemporaryFile(mode="w+b") as payload:
            for fragment in json.JSONEncoder(ensure_ascii=False, allow_nan=False).iterencode(data[field]):
                _ = payload.write(fragment.encode("utf-8"))
                if payload.tell() > MAX_PAYLOAD_BYTES:
                    raise ValueError(f"Function run {field} exceeds the {MAX_PAYLOAD_BYTES}-byte payload limit")
            size = payload.tell()
            if size <= INLINE_FIELD_BYTES:
                continue
            _ = payload.seek(0)
            digest = hashlib.sha256()
            while chunk := payload.read(64 * 1024):
                digest.update(chunk)
            checksum = base64.b64encode(digest.digest()).decode("ascii")
            upload = client.prepare_run_payload_upload(function_id, run_id, field, size_bytes=size, sha256=checksum)
            if upload.reference.size_bytes != size or upload.reference.sha256 != checksum:
                raise ValueError("Run payload upload reference does not match the local payload")
            _ = payload.seek(0)
            # The storage request never carries the API token, preview selector or capability headers.
            status = put_object(_storage_url(upload.url), payload, headers=upload.headers, timeout=(30, 300))
            if not 200 <= status < 300:
                raise ValueError("Run payload upload did not complete")
            references[field] = upload.reference.model_dump()
            if field == "result" and isinstance(data[field], str):
                data["result_preview"] = data[field][:16000]
            del data[field]
    if references:
        data["payloads"] = references
    return data


def resolve_run_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Hydrate on the caller's machine, checking the bytes before decoding JSON."""
    data = dict(data)
    references = data.pop("payloads", {})
    urls = data.pop("payload_urls", {})
    for field, raw_reference in references.items():
        if field not in PAYLOAD_FIELDS:
            raise ValueError(f"Unknown function run payload field: {field}")
        reference = UploadReference.model_validate(raw_reference)
        if not 0 < reference.size_bytes <= MAX_PAYLOAD_BYTES:
            raise ValueError("Invalid function run payload size")
        url = urls.get(field)
        if not url:
            raise ValueError(f"Missing download URL for function run payload field: {field}")
        with TemporaryFile(mode="w+b") as payload:
            digest = hashlib.sha256()
            with get_object(_storage_url(url), timeout=(30, 300), chunk_size=64 * 1024) as (status, chunks):
                if status != 200:
                    raise ValueError("Run payload download did not complete")
                for chunk in chunks:
                    if payload.tell() + len(chunk) > reference.size_bytes:
                        raise ValueError("Run payload download exceeds its declared size")
                    _ = payload.write(chunk)
                    digest.update(chunk)
            if payload.tell() != reference.size_bytes or base64.b64encode(digest.digest()).decode() != reference.sha256:
                raise ValueError("Run payload download failed size/checksum verification")
            _ = payload.seek(0)
            data[field] = json.load(payload)
    return data
