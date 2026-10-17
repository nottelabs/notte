"""Validate the operator's fixed selector map and its browser-checked proposal."""

import hashlib
import json
import re
from urllib.parse import urlsplit

MAP_PATH = "examples/github-actions/selectors.json"


def read_map(raw: bytes) -> dict:
    if len(raw) > 65_536:
        raise ValueError("Selector map exceeds 64 KiB")
    value = json.loads(raw)
    if not isinstance(value, dict) or set(value) != {"url", "selectors"}:
        raise ValueError("Expected url and selectors")
    url = urlsplit(value["url"])
    if url.scheme not in {"https", "http"} or not url.hostname or url.username or url.password:
        raise ValueError("Use an HTTP(S) page URL without credentials")
    entries = value["selectors"]
    if not isinstance(entries, dict) or not 1 <= len(entries) <= 20:
        raise ValueError("Provide 1-20 named selectors")
    for key, entry in entries.items():
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", key) or not isinstance(entry, dict):
            raise ValueError("Invalid selector entry")
        if set(entry) != {"selector", "role", "name"} or entry["role"] not in {"link", "button"}:
            raise ValueError("Each selector requires selector, role (link/button), and exact accessible name")
        for field, limit in [("selector", 2048), ("name", 256)]:
            if not isinstance(entry[field], str) or not 1 <= len(entry[field]) <= limit:
                raise ValueError("Selector or name is empty or too long")
    return value


def apply_proposal(source: bytes, raw: bytes, digest: str) -> bytes:
    if len(raw) > 131_072:
        raise ValueError("Proposal exceeds 128 KiB")
    if not re.fullmatch(r"[a-f0-9]{64}", digest) or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("Proposal digest does not match the repair job")
    document = read_map(source)
    proposal = json.loads(raw)
    if not isinstance(proposal, dict) or set(proposal) != {"version", "source_sha256", "session_id", "changes"}:
        raise ValueError("Invalid proposal fields")
    if (
        type(proposal["version"]) is not int
        or proposal["version"] != 1
        or proposal["source_sha256"] != hashlib.sha256(source).hexdigest()
    ):
        raise ValueError("Proposal is stale or has an unsupported format")
    if not isinstance(proposal["changes"], list) or len(proposal["changes"]) > len(document["selectors"]):
        raise ValueError("Invalid proposal changes")
    if not isinstance(proposal["session_id"], str) or not re.fullmatch(r"[a-f0-9-]{36}", proposal["session_id"]):
        raise ValueError("Proposal must identify its browser")
    seen = set()
    for change in proposal["changes"]:
        if not isinstance(change, dict) or set(change) != {"key", "before", "after"}:
            raise ValueError("Only selector replacements are allowed")
        key = change["key"]
        if not isinstance(key, str) or key in seen or key not in document["selectors"]:
            raise ValueError("Unknown or repeated selector key")
        if document["selectors"][key]["selector"] != change["before"]:
            raise ValueError("Original selector does not match")
        after = change["after"]
        if not isinstance(after, str) or not 1 <= len(after) <= 2048 or after == change["before"]:
            raise ValueError("Invalid replacement selector")
        seen.add(key)
        document["selectors"][key]["selector"] = after
    return (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode() if seen else source
