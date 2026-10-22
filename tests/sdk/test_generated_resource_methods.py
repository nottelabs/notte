"""Generated resource methods for the page, function-create and session-file operations.

They use the shared contract's names (`openapi/resources.json`) in snake_case, call the
operation's endpoint, and keep the core types PageClient shares with local sessions.
"""

import ast
import json
from pathlib import Path
from typing import Any

import pytest
from notte_core.actions import GotoAction
from notte_core.observation import Observation, utc_now
from notte_core.types import ExecutionResultResponse, ObserveResponse, ScrapeResponse
from notte_sdk import NotteClient
from notte_sdk.endpoints.files import FileStorageClient
from notte_sdk.errors import NotteAPIError
from notte_sdk.types import SessionFile

from tests.sdk.test_file_storage import file_metadata
from tests.sdk.test_generated_endpoints import SERVER, FakeResponse
from tests.sdk.test_vaults_codegen import client as capture_client

client = capture_client
SDK = Path(__file__).parents[2] / "packages/notte-sdk/src/notte_sdk"


class Capture:
    """A request session that records each call, including its uploaded files."""

    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self.payload: Any = payload
        self.status_code: int = status_code
        self.calls: list[dict[str, Any]] = []

    def __enter__(self) -> "Capture":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def _call(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        files = kwargs.get("files") or {}
        uploads = {
            name: (handle[0], handle[1].read())
            if isinstance(handle, tuple)
            else (Path(handle.name).name, handle.read())
            for name, handle in files.items()
        }
        self.calls.append({"method": method, "url": url.removeprefix(SERVER), **kwargs, "uploads": uploads})
        return FakeResponse(self.payload, self.status_code)

    def get(self, **kwargs: Any) -> FakeResponse:
        return self._call("GET", **kwargs)

    def post(self, **kwargs: Any) -> FakeResponse:
        return self._call("POST", **kwargs)

    def delete(self, **kwargs: Any) -> FakeResponse:
        return self._call("DELETE", **kwargs)


class BytesResponse(FakeResponse):
    def __init__(self, body: bytes) -> None:
        super().__init__(None)
        self.body: bytes = body

    @property
    def content(self) -> bytes:
        return self.body


def capture(monkeypatch: pytest.MonkeyPatch, payload: Any, status_code: int = 200) -> Capture:
    session = Capture(payload, status_code)
    monkeypatch.setattr("notte_sdk.endpoints.base.request_session", lambda: session)
    return session


def test_page_methods_call_the_page_endpoints_with_core_types(
    client: NotteClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = capture(monkeypatch, ScrapeResponse(markdown="# hi").model_dump(mode="json"))
    scraped = client.sessions.scrape("s/1", only_main_content=True, query={"update_metadata": False})
    assert isinstance(scraped, ScrapeResponse)
    assert scraped.markdown == "# hi"

    api.payload = Observation.empty().model_dump(mode="json")
    assert isinstance(client.sessions.observe("s/1", max_nb_actions=5), ObserveResponse)

    started = utc_now()
    api.payload = ExecutionResultResponse(
        action=GotoAction(url="https://example.test"), success=True, message="ok", started_at=started, ended_at=started
    ).model_dump(mode="json")
    executed = client.sessions.execute("s/1", GotoAction(url="https://example.test"), captcha_timeout_seconds=5)
    assert isinstance(executed, ExecutionResultResponse)
    assert executed.success

    assert [(c["method"], c["url"], c["params"]) for c in api.calls] == [
        ("POST", "/sessions/s%2F1/page/scrape", {"update_metadata": False}),
        ("POST", "/sessions/s%2F1/page/observe", {}),
        ("POST", "/sessions/s%2F1/page/execute", {"captcha_timeout_seconds": 5}),
    ]
    assert json.loads(api.calls[0]["data"])["only_main_content"] is True
    assert json.loads(api.calls[1]["data"])["max_nb_actions"] == 5
    assert json.loads(api.calls[2]["data"]) == GotoAction(url="https://example.test").model_dump(exclude_none=True)


def test_session_file_aliases_match_the_files_resource(
    client: NotteClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local = tmp_path / "input.txt"
    _ = local.write_text("hello")
    metadata = file_metadata().model_dump(mode="json")
    api = capture(monkeypatch, metadata, 201)

    uploaded = client.sessions.upload_session_file("session-id", file=str(local))
    assert isinstance(uploaded, SessionFile)
    api.payload, api.status_code = {"files": [metadata], "total": 1, "limit": 100, "offset": 0}, 200
    assert client.sessions.list_session_files("session-id", limit=1).total == 1
    assert client.files.list("session-id", limit=1).total == 1
    api.payload, api.status_code = None, 204
    assert client.sessions.delete_session_file("session-id", "file-id") is None

    assert [(c["method"], c["url"], c.get("params")) for c in api.calls] == [
        ("POST", "/sessions/session-id/files", None),
        ("GET", "/sessions/session-id/files", {"limit": 1}),
        ("GET", "/sessions/session-id/files", {"limit": 1}),
        ("DELETE", "/sessions/session-id/files/file-id", None),
    ]
    # The file is uploaded under its own name; the multipart form has no other fields.
    assert api.calls[0]["uploads"] == {"file": ("input.txt", b"hello")}
    assert api.calls[0]["data"] == {}


def test_download_session_file_returns_the_raw_body(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    api = capture(monkeypatch, None)
    monkeypatch.setattr(api, "_call", lambda method, url, **_: BytesResponse(b"\x00binary"))
    assert client.sessions.download_session_file("session-id", "file-id") == b"\x00binary"


def test_download_session_file_errors_are_typed(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = capture(monkeypatch, {"detail": "missing"}, 404)
    with pytest.raises(NotteAPIError) as error:
        _ = client.sessions.download_session_file("session-id", "file-id")
    assert error.value.status_code == 404


def test_upload_closes_the_local_file(client: NotteClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    local = tmp_path / "input.txt"
    _ = local.write_text("hello")
    handles: list[Any] = []
    api = capture(monkeypatch, file_metadata().model_dump(mode="json"))
    record = api._call  # pyright: ignore[reportPrivateUsage]

    def keep(method: str, url: str, **kwargs: Any) -> FakeResponse:
        handles.extend(kwargs["files"].values())
        return record(method, url, **kwargs)

    monkeypatch.setattr(api, "_call", keep)
    files: FileStorageClient = client.files
    _ = files.upload("session-id", str(local), "renamed.txt")
    [(name, handle)] = handles
    assert name == "renamed.txt"
    assert handle.closed


def test_upload_of_a_missing_file_is_rejected_before_sending(
    client: NotteClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    api = capture(monkeypatch, {})
    with pytest.raises(ValueError, match="doesn't exist"):
        _ = client.sessions.upload_session_file("session-id", file=str(tmp_path / "missing.txt"))
    assert api.calls == []


# The HTTP library is a transport detail: only these modules may import it, so swapping it
# touches nothing else. `sessions.fetch` returns the response notte_core builds (typing only).
TRANSPORT_MODULES = {"_transport.py", "_retry.py", "errors.py", "endpoints/base.py"}


def _runtime_imports(tree: ast.Module) -> set[str]:
    imported: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.If) and ast.unparse(node.test) == "TYPE_CHECKING":
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in child.names)
            elif isinstance(child, ast.ImportFrom) and child.module and child.level == 0:
                imported.add(child.module.split(".")[0])
    return imported


@pytest.mark.parametrize(
    "module",
    sorted(
        str(path.relative_to(SDK)) for path in SDK.rglob("*.py") if str(path.relative_to(SDK)) not in TRANSPORT_MODULES
    ),
)
def test_only_transport_modules_import_the_http_library(module: str) -> None:
    assert "requests" not in _runtime_imports(ast.parse((SDK / module).read_text()))
