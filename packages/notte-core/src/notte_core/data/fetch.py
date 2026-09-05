"""Issue an HTTP request from the page a session is on.

`session.fetch()` runs the browser's own `fetch()` inside the current page, so
the request carries the page's cookies, the session's proxy and the browser's
network fingerprint. This module builds the script and reads the result back
into a standard `requests.Response`; it is shared by the remote SDK session and
the local browser session.
"""

from __future__ import annotations

import io
import json
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any, cast
from urllib.parse import urlencode, urlsplit, urlunsplit

import requests
from requests.structures import CaseInsensitiveDict

from notte_core.errors.actions import FetchResponseDecodeError

FetchData = str | Mapping[str, Any]

_CONTENT_TYPE = "content-type"


def _has_header(headers: Mapping[str, str], name: str) -> bool:
    return any(key.lower() == name for key in headers)


def build_fetch_script(
    url: str,
    *,
    method: str = "GET",
    headers: Mapping[str, str] | None = None,
    params: Mapping[str, Any] | None = None,
    json_body: Any = None,
    data: FetchData | None = None,
    timeout: float | None = None,
) -> str:
    """Return the JavaScript that performs the request and serialises the response.

    The script is an async IIFE, which `evaluate_js` awaits. It returns a JSON
    string so the value survives the evaluate round-trip unchanged.
    """
    if json_body is not None and data is not None:
        raise ValueError("pass either json or data, not both")
    if timeout is not None and timeout <= 0:
        raise ValueError("timeout must be positive")

    request_url = url
    if params:
        # insert before any fragment: the browser strips `#...` before sending,
        # so parameters appended after it would be silently dropped
        parts = urlsplit(url)
        query = urlencode(params, doseq=True)
        if parts.query:
            query = f"{parts.query}&{query}"
        request_url = urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))

    request_headers: dict[str, str] = dict(headers or {})
    body: str | None = None
    if json_body is not None:
        body = json.dumps(json_body)
        if not _has_header(request_headers, _CONTENT_TYPE):
            request_headers["Content-Type"] = "application/json"
    elif isinstance(data, Mapping):
        body = urlencode(data, doseq=True)
        if not _has_header(request_headers, _CONTENT_TYPE):
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif data is not None:
        body = data

    init: dict[str, Any] = {
        "method": method.upper(),
        "headers": request_headers,
        "credentials": "include",
        "redirect": "follow",
    }
    if body is not None:
        if init["method"] in {"GET", "HEAD"}:
            # browser fetch() rejects these outright, so fail before the round-trip
            raise ValueError(f"{init['method']} requests cannot have a body")
        init["body"] = body

    abort = ""
    if timeout is not None:
        abort = (
            "const controller = new AbortController();"
            f"setTimeout(() => controller.abort(), {int(timeout * 1000)});"
            "init.signal = controller.signal;"
        )
    return (
        "(async () => {"
        f"const init = {json.dumps(init)};"
        f"{abort}"
        f"const response = await fetch({json.dumps(request_url)}, init);"
        "const text = await response.text();"
        "const headers = {};"
        "response.headers.forEach((value, key) => { headers[key] = value; });"
        "return JSON.stringify({status: response.status, url: response.url, headers: headers, text: text});"
        "})()"
    )


def response_from_evaluated(raw: str) -> requests.Response:
    """Turn the envelope `build_fetch_script` returns into a `requests.Response`.

    A non-2xx status is a response, not an error; `raise_for_status()` raises
    `requests.HTTPError` as usual. `url` is the final URL after redirects, and
    the body is exposed through `text`, `content` and `json()`.
    """
    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FetchResponseDecodeError(reason=str(exc)) from exc
    if not isinstance(payload, dict):
        raise FetchResponseDecodeError(reason="envelope is not an object")
    envelope = cast(dict[str, Any], payload)
    try:
        status_code = int(envelope["status"])
        raw_headers: Any = envelope.get("headers") or {}
        headers = {str(key): str(value) for key, value in dict(raw_headers).items()}
        text = str(envelope.get("text", ""))
        url = str(envelope.get("url", ""))
    except (KeyError, TypeError, ValueError) as exc:
        raise FetchResponseDecodeError(reason=str(exc)) from exc

    response = requests.Response()
    response.status_code = status_code
    response.headers = CaseInsensitiveDict(headers)
    # the browser already decoded the body; hand it back as utf-8 so `.text` round-trips
    response.encoding = "utf-8"
    response.raw = io.BytesIO(text.encode("utf-8"))
    response.url = url
    try:
        response.reason = HTTPStatus(status_code).phrase
    except ValueError:
        response.reason = ""
    return response
