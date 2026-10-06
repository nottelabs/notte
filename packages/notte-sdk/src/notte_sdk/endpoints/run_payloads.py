"""Transfer large run fields directly to object storage, outside API requests."""

import base64
import hashlib
import json
from tempfile import TemporaryFile
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlsplit

import requests
from pydantic import BaseModel, RootModel

from notte_sdk.endpoints.base import NotteEndpoint

if TYPE_CHECKING:
    from notte_sdk.endpoints.base import BaseClient

INLINE_FIELD_BYTES = 1024 * 1024
MAX_PAYLOAD_BYTES = 256 * 1024 * 1024
PAYLOAD_FIELDS = ("result", "logs", "variables")


class PayloadMode(BaseModel):
    payload_mode: Literal["references"] = "references"


class RunUpdateBody(RootModel[dict[str, Any]]):
    pass


class UploadReference(BaseModel):
    upload_id: str
    size_bytes: int
    sha256: str


class UploadResponse(BaseModel):
    reference: UploadReference
    url: str
    headers: dict[str, str]


def _storage_url(url: str) -> str:
    # Never forward API credentials to an object URL, or follow its redirects.
    if urlsplit(url).scheme != "https":
        raise ValueError("Run payload storage requires an HTTPS URL")
    return url


def offload_run_fields(client: "BaseClient", path: str, fields: dict[str, Any]) -> dict[str, Any]:
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
            upload = client.request(
                NotteEndpoint(
                    path=f"{path}/payloads/{field}/upload",
                    method="POST",
                    response=UploadResponse,
                    request=RunUpdateBody({"size_bytes": size, "sha256": checksum}),
                )
            )
            if upload.reference.size_bytes != size or upload.reference.sha256 != checksum:
                raise ValueError("Run payload upload reference does not match the local payload")
            _ = payload.seek(0)
            # A separate session keeps the API token, preview selector and
            # capability headers out of the storage request.
            with requests.Session() as storage_session:
                with storage_session.put(
                    _storage_url(upload.url),
                    data=payload,
                    headers=upload.headers,
                    timeout=(30, 300),
                    allow_redirects=False,
                ) as response:
                    response.raise_for_status()
                    if not 200 <= response.status_code < 300:
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
            with requests.Session() as storage_session:
                with storage_session.get(
                    _storage_url(url), stream=True, timeout=(30, 300), allow_redirects=False
                ) as response:
                    response.raise_for_status()
                    if response.status_code != 200:
                        raise ValueError("Run payload download did not complete")
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        if payload.tell() + len(chunk) > reference.size_bytes:
                            raise ValueError("Run payload download exceeds its declared size")
                        _ = payload.write(chunk)
                        digest.update(chunk)
            if payload.tell() != reference.size_bytes or base64.b64encode(digest.digest()).decode() != reference.sha256:
                raise ValueError("Run payload download failed size/checksum verification")
            _ = payload.seek(0)
            data[field] = json.load(payload)
    return data
