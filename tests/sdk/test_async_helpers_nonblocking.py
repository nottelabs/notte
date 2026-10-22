"""The SDK's `async def` helpers must not run blocking HTTP calls on the caller's event loop."""

import asyncio
import threading
from collections.abc import Callable, Coroutine
from types import SimpleNamespace
from typing import ParamSpec, TypeVar
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from notte_core.credentials.base import Credential, CredentialsDict, CreditCardDict
from notte_sdk.endpoints import sessions
from notte_sdk.endpoints.files import RemoteFileStorage
from notte_sdk.endpoints.personas import NottePersona
from notte_sdk.endpoints.sessions import RemoteSession
from notte_sdk.endpoints.vaults import NotteVault

from tests.sdk.test_file_storage import file_metadata

P = ParamSpec("P")
T = TypeVar("T")

# How long a stubbed call blocks unless the event loop releases it. A blocked loop fails after this.
BLOCK_TIMEOUT = 2.0


class LoopProbe:
    """Stands in for a sync HTTP call: it blocks until a coroutine on the event loop releases it."""

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.released = threading.Event()
        self.released_while_blocked: list[bool] = []

    def blocking(self, result: T) -> Callable[P, T]:
        def call(*_args: P.args, **_kwargs: P.kwargs) -> T:
            self.entered.set()
            self.released_while_blocked.append(self.released.wait(BLOCK_TIMEOUT))
            return result

        return call

    async def run(self, helper: Coroutine[None, None, T]) -> T:
        async def release() -> None:
            # Runs only while the event loop is free. If the helper blocks the loop, the stub has
            # already timed out by the time this gets a turn.
            while not self.entered.is_set():
                await asyncio.sleep(0.001)
            self.released.set()

        result, _ = await asyncio.gather(helper, release())
        assert self.released_while_blocked, "the stubbed call never ran"
        assert all(self.released_while_blocked), "the helper blocked the event loop"
        return result


def vault(client: Mock) -> NotteVault:
    client.get.return_value = "vault-id"
    return NotteVault(vault_id="vault-id", _client=client)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "response", "call"),
    [
        ("credentials_add", None, lambda v: v.add_credentials_async("example.com", username="ada")),
        (
            "credentials_get",
            SimpleNamespace(credentials={"username": "ada"}),
            lambda v: v.get_credentials_async("example.com"),
        ),
        ("credentials_delete", None, lambda v: v.delete_credentials_async("example.com")),
        ("credentials_list", SimpleNamespace(credentials=[]), lambda v: v.list_credentials_async()),
        ("credit_card_set", None, lambda v: v.set_credit_card_async(card_holder_name="Ada")),
        (
            "credit_card_get",
            SimpleNamespace(credit_card={"card_holder_name": "Ada"}),
            lambda v: v.get_credit_card_async(),
        ),
        ("credit_card_delete", None, lambda v: v.delete_credit_card_async()),
    ],
)
async def test_vault_async_helpers_run_off_the_event_loop(
    operation: str,
    response: SimpleNamespace | None,
    call: Callable[[NotteVault], Coroutine[None, None, CredentialsDict | CreditCardDict | list[Credential] | None]],
) -> None:
    probe = LoopProbe()
    client = Mock()
    getattr(client, operation).side_effect = probe.blocking(response)
    _ = await probe.run(call(vault(client)))
    getattr(client, operation).assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(("operation", "helper"), [("emails_list", "aemails"), ("sms_list", "asms")])
async def test_persona_async_reads_run_off_the_event_loop(operation: str, helper: str) -> None:
    probe = LoopProbe()
    client = MagicMock()
    getattr(client.personas, operation).side_effect = probe.blocking(["message"])
    client.personas.get.return_value.persona_id = "persona-id"
    persona = NottePersona("persona-id", _client=client)
    assert await probe.run(getattr(persona, helper)(only_unread=True)) == ["message"]
    getattr(client.personas, operation).assert_called_once_with("persona-id", only_unread=True)


@pytest.mark.asyncio
async def test_persona_await_emails_polls_off_the_event_loop() -> None:
    probe = LoopProbe()
    client = MagicMock()
    client.personas.emails_list.side_effect = probe.blocking(["message"])
    persona = NottePersona("persona-id", _client=client)
    assert await probe.run(persona.await_emails(timeout=5, poll_interval=0)) == ["message"]


def file_storage(client: Mock) -> RemoteFileStorage:
    return RemoteFileStorage("session-id", _client=client)


@pytest.mark.asyncio
async def test_file_storage_get_file_runs_off_the_event_loop() -> None:
    # One probe per call: a released probe stays released, so a shared one would not check the download.
    listing, download = LoopProbe(), LoopProbe()
    client = Mock()
    client.list.side_effect = listing.blocking(SimpleNamespace(files=[file_metadata()]))
    client.download.side_effect = download.blocking("/tmp/input.txt")
    assert await download.run(listing.run(file_storage(client).get_file("input.txt"))) == "/tmp/input.txt"
    assert len(listing.released_while_blocked) == len(download.released_while_blocked) == 1


@pytest.mark.asyncio
async def test_file_storage_set_file_runs_off_the_event_loop() -> None:
    probe = LoopProbe()
    client = Mock()
    client.upload.side_effect = probe.blocking(file_metadata())
    assert await probe.run(file_storage(client).set_file("input.txt")) is True
    client.upload.assert_called_once_with("session-id", "input.txt", None)


@pytest.mark.asyncio
@pytest.mark.parametrize("helper", ["alist_uploaded_files", "alist_downloaded_files"])
async def test_file_storage_listing_runs_off_the_event_loop(helper: str) -> None:
    probe = LoopProbe()
    client = Mock()
    client.list.side_effect = probe.blocking(SimpleNamespace(files=[file_metadata()]))
    files = await probe.run(getattr(file_storage(client), helper)())
    assert [file.name for file in files] == ["input.txt"]


def bare_session() -> RemoteSession:
    session = object.__new__(RemoteSession)
    session.request = SimpleNamespace(cdp_url=None)
    session.client = SimpleNamespace(server_url="https://notte.example", REQUEST_ORIGIN="sdk-python")
    session._playwright_browser = None
    session._playwright_context = None
    session._playwright_page = None
    session._async_playwright_browser = None
    session._async_playwright_context = None
    session._async_playwright_page = None
    return session


@pytest.mark.asyncio
async def test_async_context_exit_stops_the_session_off_the_event_loop() -> None:
    probe = LoopProbe()
    session = bare_session()
    session.stop = MagicMock(side_effect=probe.blocking(None))
    await probe.run(session.__aexit__(None, None, None))
    session.stop.assert_called_once_with(close_reason="manual")


@pytest.mark.asyncio
async def test_cancelled_async_context_exit_waits_for_the_session_stop() -> None:
    entered, release = threading.Event(), threading.Event()
    stopped: list[bool] = []

    def stop(**_kwargs: str) -> None:
        entered.set()
        _ = release.wait(BLOCK_TIMEOUT)
        stopped.append(True)

    session = bare_session()
    session.stop = MagicMock(side_effect=stop)
    exit_task = asyncio.create_task(session.__aexit__(None, None, None))
    while not entered.is_set():
        await asyncio.sleep(0.001)
    _ = exit_task.cancel()
    await asyncio.sleep(0.01)
    assert not exit_task.done(), "the exit returned while the session was still stopping"
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await exit_task
    assert stopped == [True]


@pytest.mark.asyncio
async def test_async_page_resolves_the_cdp_url_off_the_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    probe = LoopProbe()
    session = bare_session()
    session.cdp_url = MagicMock(side_effect=probe.blocking("wss://notte.example/cdp"))
    page = MagicMock()
    browser = MagicMock()
    browser.contexts = [SimpleNamespace(pages=[page], on=MagicMock())]
    playwright = MagicMock()
    playwright.chromium.connect_over_cdp = AsyncMock(return_value=browser)
    starter = MagicMock()
    starter.start = AsyncMock(return_value=playwright)
    monkeypatch.setattr(sessions, "_async_playwright_available", True)
    monkeypatch.setattr(sessions, "_async_playwright", MagicMock(return_value=starter))
    monkeypatch.delenv("NOTTE_AUTH_CAPABILITY", raising=False)

    async def open_page() -> MagicMock:
        return await session.apage

    assert await probe.run(open_page()) is page
