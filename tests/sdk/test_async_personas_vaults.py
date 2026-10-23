"""`AsyncNotteClient` personas, vaults, managed auth and `health_check`: the sync methods, as coroutines.

Each scenario runs once through `NotteClient` and once through `AsyncNotteClient` behind the same
scripted API, and must send the same requests, sleep the same delays and return or raise the same thing.
"""

import asyncio
import inspect
import json
from collections.abc import Awaitable, Callable
from functools import cached_property
from typing import Any

import httpx
import pytest
from notte_core.credentials.base import BaseVault
from notte_sdk import AsyncNotteClient, NotteClient
from notte_sdk._transport import AsyncSharedHttpClient, SharedHttpClient, async_http_client
from notte_sdk.endpoints._async_resource import AwaitableResource
from notte_sdk.endpoints.base import AsyncBaseClient, BaseClient
from notte_sdk.endpoints.managed_auth import AsyncManagedAuthClient, ManagedAuthClient
from notte_sdk.endpoints.personas import AsyncNottePersona, BasePersona, NottePersona
from notte_sdk.endpoints.vaults import AsyncNotteVault, NotteVault

from tests.sdk.test_async_resources import KEY, STAMP, Exchange, exchange_async, exchange_sync, normalize
from tests.sdk.test_generated_endpoints import PERSONA, SERVER, VAULT

Routes = dict[tuple[str, str], list[Any]]

VAULT_PERSONA = {**PERSONA, "vault_id": "vault-1"}
EMAIL = dict(subject="code", email_id="e-1", created_at=STAMP, sender_email="a@x.test", sender_name=None)
SMS = dict(body="123456", sms_id="s-1", created_at=STAMP, sender="+15550000")
CREDENTIALS = {"email": "ada@example.test", "password": "hunter2"}  # pragma: allowlist secret
CARD = {
    "card_holder_name": "Ada Lovelace",
    "card_number": "4242424242424242",
    "card_cvv": "123",
    "card_full_expiration": "12/30",
}
OPERATION = dict(id="op-1", connection_id="c-1", source="sdk", phase="login", deadline=STAMP)


# ---------------------------------------------------------------------------
# Same methods, same signatures

# Public methods that do no I/O: the same plain method on both objects.
NO_IO = {
    "contains_credentials",
    "credential_fields_to_dict",
    "credentials_dict_to_field",
    "generate_password",
    "get_replacement_map",
    "has_unresolved_placeholders",
    "past_credentials",
    "patch_structured_completion",
    "recursive_replace_mapping",
}
# `with obj:` is `async with obj:` (or `await obj`) on the async objects.
CONTEXT_MANAGER = {"__enter__": "__aenter__", "__exit__": "__aexit__"}
# Instance attributes of the sync object that are properties of the async one: the async vault has
# no id until it is created, so `vault_id` raises until then.
ATTRIBUTES = {"vault_id"}

# (sync class, async class, base whose members are compared by the resource tests)
STATEFUL = [
    (NottePersona, AsyncNottePersona, None),
    (NotteVault, AsyncNotteVault, None),
    (ManagedAuthClient, AsyncManagedAuthClient, (BaseClient, AsyncBaseClient)),
]


def public_names(cls: type, base: type | None) -> set[str]:
    names = {name for name in dir(cls) if not name.startswith("_")} | (set(CONTEXT_MANAGER) & set(dir(cls)))
    return names - set(dir(base)) if base is not None else names


@pytest.mark.parametrize("sync_cls,async_cls,bases", STATEFUL, ids=lambda value: getattr(value, "__name__", ""))
def test_async_objects_have_every_sync_method_as_a_coroutine(
    sync_cls: type, async_cls: type, bases: tuple[type, type] | None
) -> None:
    sync_base, async_base = bases or (None, None)
    sync_names = public_names(sync_cls, sync_base)
    async_names = public_names(async_cls, async_base)
    assert {CONTEXT_MANAGER.get(name, name) for name in sync_names} <= async_names | {"__aenter__", "__aexit__"}
    assert async_names - sync_names <= ATTRIBUTES, async_names - sync_names
    for name in sorted(sync_names):
        if name in CONTEXT_MANAGER:
            assert inspect.iscoroutinefunction(getattr(async_cls, CONTEXT_MANAGER[name])), name
            continue
        sync_member = inspect.getattr_static(sync_cls, name)
        async_member = inspect.getattr_static(async_cls, name)
        if isinstance(sync_member, (property, cached_property)):
            assert isinstance(async_member, (property, cached_property)), name
            continue
        sync_function = getattr(sync_cls, name)
        async_function = getattr(async_cls, name)
        if name in NO_IO:
            assert not inspect.iscoroutinefunction(sync_function), name
            assert not inspect.iscoroutinefunction(async_function), name
        else:
            assert inspect.iscoroutinefunction(async_function), name
        sync_signature = inspect.signature(sync_function, eval_str=True)
        async_signature = inspect.signature(async_function, eval_str=True)
        assert async_signature.parameters == sync_signature.parameters, name
        assert async_signature.return_annotation == sync_signature.return_annotation, name


def test_async_objects_implement_the_core_interfaces() -> None:
    assert issubclass(AsyncNotteVault, BaseVault) and not inspect.isabstract(AsyncNotteVault)
    assert issubclass(AsyncNottePersona, BasePersona) and not inspect.isabstract(AsyncNottePersona)
    assert issubclass(AsyncNotteVault, AwaitableResource) and issubclass(AsyncNottePersona, AwaitableResource)
    for name in ("aemails", "asms", "await_emails", "await_sms"):
        assert inspect.iscoroutinefunction(getattr(AsyncNottePersona, name)), name
    # The persona's vault is typed as the async vault, so `await persona.vault.get_credentials(...)` checks.
    assert inspect.get_annotations(AsyncNottePersona.vault.func, eval_str=True)["return"] is AsyncNotteVault


def test_async_factories_build_the_async_objects() -> None:
    client = AsyncNotteClient(api_key=KEY, server_url=SERVER)
    assert isinstance(client.Persona("persona-1"), AsyncNottePersona)
    assert isinstance(client.Vault("vault-1"), AsyncNotteVault)
    assert isinstance(client.managed_auth, AsyncManagedAuthClient)
    assert client.managed_auth.root_client is client
    assert client.managed_auth.base_endpoint_path == NotteClient(api_key=KEY).managed_auth.base_endpoint_path


# ---------------------------------------------------------------------------
# A scripted API


class Api:
    """Answers each `(method, path)` with the next of its queued answers; the last one repeats."""

    def __init__(self, routes: Routes) -> None:
        self.routes: Routes = routes
        self.counts: dict[tuple[str, str], int] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        key = (request.method, request.url.path)
        answers = self.routes.get(key)
        if answers is None:
            return httpx.Response(404, json={"detail": f"no route for {key}"})
        index = self.counts.get(key, 0)
        self.counts[key] = index + 1
        answer = answers[min(index, len(answers) - 1)]
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, httpx.Response):
            return httpx.Response(answer.status_code, content=answer.content, headers=answer.headers)
        return httpx.Response(200, json=answer)


def no_sync_io(_: SharedHttpClient) -> httpx.Client:
    raise AssertionError("the async client sent a request through the sync transport")


async def run_async(
    monkeypatch: pytest.MonkeyPatch, routes: Routes, call: Callable[[AsyncNotteClient], Awaitable[Any]]
) -> Exchange:
    """`exchange_async`, failing if the async scenario reaches the sync transport."""
    with monkeypatch.context() as patch:
        patch.setattr(SharedHttpClient, "get", no_sync_io)
        return await exchange_async(monkeypatch, Api(routes), call)


async def assert_same(
    monkeypatch: pytest.MonkeyPatch,
    routes: Routes,
    sync_call: Callable[[NotteClient], Any],
    async_call: Callable[[AsyncNotteClient], Awaitable[Any]],
) -> Exchange:
    """Run the sync and the async scenario, each against a fresh copy of `routes`; both must match."""
    expected = exchange_sync(monkeypatch, Api(routes), sync_call)
    actual = await run_async(monkeypatch, routes, async_call)
    assert actual == expected
    assert expected.calls, expected.outcome
    return expected


def paths(exchange: Exchange) -> list[tuple[str, str]]:
    return [(call.method, call.url.removeprefix(SERVER).split("?")[0]) for call in exchange.calls]


@pytest.fixture(autouse=True)
def fixed_password(monkeypatch: pytest.MonkeyPatch) -> None:
    """Generated passwords travel in request bodies: make them the same on both sides."""
    monkeypatch.setattr("notte_sdk.endpoints.vaults.secrets.token_urlsafe", lambda n: ("aB3-" * n)[:n])


# ---------------------------------------------------------------------------
# Personas

PERSONA_ROUTES: Routes = {
    ("POST", "/personas/create"): [VAULT_PERSONA],
    ("GET", "/personas/persona-1"): [VAULT_PERSONA],
    ("DELETE", "/personas/persona-1"): [{"status": "success", "message": "deleted"}],
    ("GET", "/personas/persona-1/emails"): [[EMAIL]],
    ("GET", "/personas/persona-1/sms"): [[SMS]],
    ("POST", "/personas/persona-1/sms/number"): [{"phone_number": "+15550001", "status": "success"}],
    ("DELETE", "/personas/persona-1/sms/number"): [{"status": "success"}],
    ("GET", "/vaults/vault-1"): [{"credentials": []}],
    ("POST", "/vaults/vault-1/credentials"): [{"status": "success"}],
}


def sync_persona_flow(c: NotteClient) -> list[Any]:
    persona = c.Persona(create_vault=True)
    out: list[Any] = [persona.info, persona.persona_id, persona.email, persona.internal_email, persona.has_vault]
    out.append(persona.emails(only_unread=True, limit=5))
    out.append(persona.sms(limit=2))
    out.append(persona.create_number())
    out.append(persona.delete_number())
    persona.add_credentials("https://x.test")
    out.append(persona.vault.vault_id)
    persona.delete()
    return out


async def async_persona_flow(c: AsyncNotteClient) -> list[Any]:
    persona = await c.Persona(create_vault=True)
    out: list[Any] = [persona.info, persona.persona_id, persona.email, persona.internal_email, persona.has_vault]
    out.append(await persona.emails(only_unread=True, limit=5))
    out.append(await persona.sms(limit=2))
    out.append(await persona.create_number())
    out.append(await persona.delete_number())
    await persona.add_credentials("https://x.test")
    out.append((await persona.vault).vault_id)
    await persona.delete()
    return out


@pytest.mark.asyncio
async def test_persona_methods_send_the_same_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    exchange = await assert_same(monkeypatch, PERSONA_ROUTES, sync_persona_flow, async_persona_flow)
    assert exchange.outcome[0] == "ok", exchange.outcome
    assert paths(exchange) == [
        ("POST", "/personas/create"),
        ("GET", "/personas/persona-1/emails"),
        ("GET", "/personas/persona-1/sms"),
        ("POST", "/personas/persona-1/sms/number"),
        ("DELETE", "/personas/persona-1/sms/number"),
        ("GET", "/vaults/vault-1"),
        ("POST", "/vaults/vault-1/credentials"),
        ("GET", "/vaults/vault-1"),
        ("DELETE", "/personas/persona-1"),
    ]
    body = json.loads(exchange.calls[6].data or "{}")
    assert body["credentials"]["email"] == PERSONA["email"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "delete_answer,outcome",
    [
        ({"status": "success", "message": "deleted"}, "ok"),
        (httpx.Response(404, json={"detail": "Persona already deleted"}), "ok"),
        (httpx.Response(500, json={"detail": "boom"}), "error"),
    ],
    ids=["deleted", "already-deleted", "error"],
)
async def test_persona_context_manager_fetches_then_deletes(
    monkeypatch: pytest.MonkeyPatch, delete_answer: Any, outcome: str
) -> None:
    routes = {**PERSONA_ROUTES, ("DELETE", "/personas/persona-1"): [delete_answer]}

    def sync_call(c: NotteClient) -> Any:
        with c.Persona("persona-1") as persona:
            return persona.emails()

    async def async_call(c: AsyncNotteClient) -> Any:
        async with c.Persona("persona-1") as persona:
            return await persona.emails()

    exchange = await assert_same(monkeypatch, routes, sync_call, async_call)
    assert [call.method for call in exchange.calls] == ["GET", "GET", "DELETE"]
    assert exchange.outcome[0] == outcome


@pytest.mark.asyncio
async def test_persona_without_vault_raises_the_same_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    routes = {**PERSONA_ROUTES, ("GET", "/personas/persona-1"): [PERSONA]}

    async def async_add(c: AsyncNotteClient) -> None:
        await (await c.Persona("persona-1")).add_credentials("https://x.test")

    exchange = await assert_same(
        monkeypatch, routes, lambda c: c.Persona("persona-1").add_credentials("https://x.test"), async_add
    )
    assert exchange.outcome[1] is ValueError

    async def async_vault(c: AsyncNotteClient) -> Any:
        return (await c.Persona("persona-1")).vault

    exchange = await assert_same(monkeypatch, routes, lambda c: c.Persona("persona-1").vault, async_vault)
    assert exchange.outcome[1] is ValueError


def test_unstarted_async_objects_send_nothing() -> None:
    client = AsyncNotteClient(api_key=KEY, server_url=SERVER)
    with pytest.raises(ValueError, match="Persona not initialized"):
        _ = client.Persona(create_vault=True).persona_id
    with pytest.raises(ValueError, match="Vault not created yet"):
        _ = client.Vault().vault_id
    # A known vault id can be used without the existence check.
    assert client.Vault("vault-1").vault_id == "vault-1"


# ---------------------------------------------------------------------------
# Polling


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["emails", "sms"])
async def test_wait_helpers_poll_the_same_way(monkeypatch: pytest.MonkeyPatch, kind: str) -> None:
    message = EMAIL if kind == "emails" else SMS
    routes = {**PERSONA_ROUTES, ("GET", f"/personas/persona-1/{kind}"): [[], [], [message]]}

    def sync_call(c: NotteClient) -> Any:
        return getattr(c.Persona("persona-1"), f"wait_for_{kind}")(only_unread=True, timeout=60, poll_interval=2)

    async def async_call(c: AsyncNotteClient) -> Any:
        persona = await c.Persona("persona-1")
        return await getattr(persona, f"wait_for_{kind}")(only_unread=True, timeout=60, poll_interval=2)

    exchange = await assert_same(monkeypatch, routes, sync_call, async_call)
    assert exchange.sleeps == [2, 2]
    assert paths(exchange).count(("GET", f"/personas/persona-1/{kind}")) == 3
    assert exchange.calls[-1].params == {"only_unread": "True"}

    # The `BasePersona` interface a local session uses polls the same way.
    async def await_call(c: AsyncNotteClient) -> Any:
        persona = await c.Persona("persona-1")
        return await getattr(persona, f"await_{kind}")(only_unread=True, timeout=60, poll_interval=2)

    assert await run_async(monkeypatch, routes, await_call) == exchange


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["emails", "sms"])
async def test_wait_helpers_time_out_the_same_way(monkeypatch: pytest.MonkeyPatch, kind: str) -> None:
    routes = {**PERSONA_ROUTES, ("GET", f"/personas/persona-1/{kind}"): [[]]}
    clock = [0.0]

    def advance(delay: float) -> None:
        clock[0] += delay

    async def aadvance(delay: float) -> None:
        clock[0] += delay

    def sync_call(c: NotteClient) -> Any:
        persona = c.Persona("persona-1")
        clock[0] = 0.0
        with monkeypatch.context() as patch:
            patch.setattr("notte_sdk.endpoints.personas.time.monotonic", lambda: clock[0])
            patch.setattr("notte_sdk.endpoints.personas.time.sleep", advance)
            return getattr(persona, f"wait_for_{kind}")(timeout=10, poll_interval=3)

    async def async_call(c: AsyncNotteClient) -> Any:
        persona = await c.Persona("persona-1")
        clock[0] = 0.0
        with monkeypatch.context() as patch:
            patch.setattr("notte_sdk.endpoints.personas.time.monotonic", lambda: clock[0])
            patch.setattr("notte_sdk.endpoints.personas.asyncio.sleep", aadvance)
            return await getattr(persona, f"wait_for_{kind}")(timeout=10, poll_interval=3)

    exchange = await assert_same(monkeypatch, routes, sync_call, async_call)
    assert exchange.outcome[1] is TimeoutError
    # Polled at 0, 3, 6 and 9; another poll at 12 would pass the 10 s deadline.
    assert paths(exchange).count(("GET", f"/personas/persona-1/{kind}")) == 4


@pytest.mark.asyncio
async def test_persona_inbox_reads_overlap_on_one_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """`aemails`/`asms`/`await_emails` are real coroutines: concurrent reads are in flight together."""
    in_flight = 0
    peak = 0
    started = asyncio.Event()

    async def handle(request: httpx.Request) -> httpx.Response:
        nonlocal in_flight, peak
        if request.url.path == "/personas/persona-1":
            return httpx.Response(200, json=VAULT_PERSONA)
        in_flight += 1
        peak = max(peak, in_flight)
        if in_flight == 3:
            started.set()
        # Every read waits until all three are in flight: sequential reads would never finish.
        await asyncio.wait_for(started.wait(), timeout=5)
        in_flight -= 1
        return httpx.Response(200, json=[EMAIL] if request.url.path.endswith("emails") else [SMS])

    client = async_http_client()
    client._transport = httpx.MockTransport(handle)
    monkeypatch.setattr(AsyncSharedHttpClient, "get", lambda _: client)
    monkeypatch.setattr(SharedHttpClient, "get", no_sync_io)
    async with AsyncNotteClient(api_key=KEY, server_url=SERVER) as notte:
        persona = await notte.Persona("persona-1")
        emails, sms, waited = await asyncio.gather(persona.aemails(), persona.asms(), persona.await_emails(timeout=5))
    assert (emails[0].email_id, sms[0].sms_id, waited[0].email_id) == ("e-1", "s-1", "e-1")
    assert peak == 3
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["vault", "persona"])
async def test_concurrent_starts_create_one_resource(monkeypatch: pytest.MonkeyPatch, kind: str) -> None:
    """Tasks awaiting the same new object share one create: a second create would leak, never deleted."""
    creates = 0
    release = asyncio.Event()

    async def handle(request: httpx.Request) -> httpx.Response:
        nonlocal creates
        creates += 1
        # Hold the first create open, so an unguarded second start would send its own.
        await asyncio.wait_for(release.wait(), timeout=5)
        return httpx.Response(200, json=VAULT if kind == "vault" else VAULT_PERSONA)

    client = async_http_client()
    client._transport = httpx.MockTransport(handle)
    monkeypatch.setattr(AsyncSharedHttpClient, "get", lambda _: client)
    async with AsyncNotteClient(api_key=KEY, server_url=SERVER) as notte:
        resource = notte.Vault(name="v") if kind == "vault" else notte.Persona()
        starts = asyncio.gather(resource.start(), resource.start(), resource.start())
        await asyncio.sleep(0.05)
        release.set()
        _ = await starts
    assert creates == 1
    await client.aclose()


# ---------------------------------------------------------------------------
# Vaults

VAULT_ROUTES: Routes = {
    ("POST", "/vaults/create"): [VAULT],
    ("DELETE", "/vaults/vault-1"): [{"status": "success", "message": "gone"}],
    ("GET", "/vaults/vault-1"): [{"credentials": [{"url": "https://x.test", "email": None, "username": None}]}],
    ("POST", "/vaults/vault-1/credentials"): [{"status": "success"}],
    ("GET", "/vaults/vault-1/credentials"): [{"credentials": CREDENTIALS}],
    ("DELETE", "/vaults/vault-1/credentials"): [{"status": "success"}],
    ("POST", "/vaults/vault-1/card"): [{"status": "success"}],
    ("GET", "/vaults/vault-1/card"): [{"credit_card": CARD}],
    ("DELETE", "/vaults/vault-1/card"): [{"status": "success"}],
}


def sync_vault_flow(c: NotteClient) -> list[Any]:
    vault = c.Vault(name="v")
    out: list[Any] = [vault.vault_id]
    vault.add_credentials("https://x.test", **CREDENTIALS)
    vault.add_credentials_from_env("https://x.test")
    out.append(vault.get_credentials("https://x.test"))
    out.append(vault.list_credentials())
    out.append(vault.has_credential("https://x.test"))
    vault.delete_credentials("https://x.test")
    vault.set_credit_card(**CARD)
    out.append(vault.get_credit_card())
    vault.delete_credit_card()
    out.append(vault.get_replacement_map())
    out.append(vault.past_credentials())
    out.append(len(vault.generate_password(12)))
    vault.stop()
    return out


async def async_vault_flow(c: AsyncNotteClient) -> list[Any]:
    vault = await c.Vault(name="v")
    out: list[Any] = [vault.vault_id]
    await vault.add_credentials("https://x.test", **CREDENTIALS)
    await vault.add_credentials_from_env("https://x.test")
    out.append(await vault.get_credentials("https://x.test"))
    out.append(await vault.list_credentials())
    out.append(await vault.has_credential("https://x.test"))
    await vault.delete_credentials("https://x.test")
    await vault.set_credit_card(**CARD)
    out.append(await vault.get_credit_card())
    await vault.delete_credit_card()
    out.append(vault.get_replacement_map())
    out.append(vault.past_credentials())
    out.append(len(vault.generate_password(12)))
    await vault.stop()
    return out


@pytest.mark.asyncio
async def test_vault_methods_send_the_same_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_EMAIL", "env@x.test")
    exchange = await assert_same(monkeypatch, VAULT_ROUTES, sync_vault_flow, async_vault_flow)
    assert exchange.outcome[0] == "ok", exchange.outcome
    replacement_map = exchange.outcome[1][-3]
    # Retrieved values are tracked for redaction: each maps back to its placeholder.
    assert set(replacement_map) == {"ada@example.test", "hunter2"}
    assert paths(exchange)[0] == ("POST", "/vaults/create")
    assert paths(exchange)[-1] == ("DELETE", "/vaults/vault-1")


@pytest.mark.asyncio
async def test_vault_core_interface_sends_the_same_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    """The `BaseVault` coroutines a local session awaits, against the sync vault's own."""

    async def run(vault: BaseVault) -> list[Any]:
        out: list[Any] = [
            await vault.get_credentials_async("https://x.test"),
            await vault.list_credentials_async(),
            await vault.get_credit_card_async(),
            await vault.has_credential_async("https://x.test"),
        ]
        await vault.add_credentials_async("https://x.test", **CREDENTIALS)
        await vault.set_credit_card_async(**CARD)
        await vault.delete_credentials_async("https://x.test")
        await vault.delete_credit_card_async()
        return [*out, vault.get_replacement_map()]

    async def async_call(c: AsyncNotteClient) -> list[Any]:
        return await run(await c.Vault("vault-1"))

    # The sync vault's coroutines block on the sync transport: run them on a thread with its own loop.
    expected = await asyncio.to_thread(
        exchange_sync, monkeypatch, Api(VAULT_ROUTES), lambda c: asyncio.run(run(c.Vault("vault-1")))
    )
    actual = await run_async(monkeypatch, VAULT_ROUTES, async_call)
    assert actual == expected
    assert expected.outcome[0] == "ok", expected.outcome


@pytest.mark.asyncio
@pytest.mark.parametrize("vault_id", ["vault-1", ""])
async def test_vault_lookup_checks_the_id_the_same_way(monkeypatch: pytest.MonkeyPatch, vault_id: str) -> None:
    async def async_call(c: AsyncNotteClient) -> Any:
        return [(await c.Vault(vault_id)).vault_id, await c.vaults.get(vault_id)]

    exchange_s = exchange_sync(
        monkeypatch, Api(VAULT_ROUTES), lambda c: [c.Vault(vault_id).vault_id, c.vaults.get(vault_id)]
    )
    exchange_a = await run_async(monkeypatch, VAULT_ROUTES, async_call)
    assert exchange_a == exchange_s
    assert len(exchange_s.calls) == (2 if vault_id else 0)


@pytest.mark.asyncio
async def test_awaiting_again_does_not_create_again(monkeypatch: pytest.MonkeyPatch) -> None:
    async def async_call(c: AsyncNotteClient) -> str:
        vault = await c.Vault(name="v")
        assert await vault is vault
        async with vault:
            pass
        return vault.vault_id

    exchange = await run_async(monkeypatch, VAULT_ROUTES, async_call)
    assert paths(exchange) == [("POST", "/vaults/create"), ("DELETE", "/vaults/vault-1")]


# ---------------------------------------------------------------------------
# Managed auth and health check


def operation(status: str, **extra: Any) -> dict[str, Any]:
    return {**OPERATION, "status": status, **extra}


@pytest.mark.asyncio
@pytest.mark.parametrize("final", ["succeeded", "failed"])
@pytest.mark.parametrize("action", ["refresh", "reauthenticate"])
async def test_managed_auth_waits_the_same_way(monkeypatch: pytest.MonkeyPatch, action: str, final: str) -> None:
    routes: Routes = {
        ("POST", "/managed-auth/connections/c-1/check"): [
            {"connection_id": "c-1", "status": "ok", "message": "fine", "authenticated": True}
        ],
        ("POST", f"/managed-auth/connections/c-1/{action}"): [operation("pending")],
        ("GET", "/managed-auth/operations/op-1"): [operation("running"), operation(final, error="bad password")],
    }
    method = f"{action}_connection"

    def sync_call(c: NotteClient) -> list[Any]:
        return [
            c.managed_auth.check_connection("c-1"),
            getattr(c.managed_auth, method)("c-1", wait=False, auth_retry=2),
            getattr(c.managed_auth, method)("c-1"),
        ]

    async def async_call(c: AsyncNotteClient) -> list[Any]:
        return [
            await c.managed_auth.check_connection("c-1"),
            await getattr(c.managed_auth, method)("c-1", wait=False, auth_retry=2),
            await getattr(c.managed_auth, method)("c-1"),
        ]

    exchange = await assert_same(monkeypatch, routes, sync_call, async_call)
    assert exchange.outcome[0] == ("ok" if final == "succeeded" else "error")
    assert exchange.sleeps == [1, 1]
    assert json.loads(exchange.calls[1].data or "{}") == {"auth_retry": 2}
    assert json.loads(exchange.calls[2].data or "{}") == {}
    assert exchange.calls[3].timeout == {"connect": 10, "read": 10, "write": 10, "pool": 10}


@pytest.mark.asyncio
async def test_managed_auth_times_out_the_same_way(monkeypatch: pytest.MonkeyPatch) -> None:
    routes: Routes = {("GET", "/managed-auth/operations/op-1"): [operation("running")]}
    clock = [0.0]

    def tick() -> float:
        clock[0] += 1
        return clock[0]

    def sync_call(c: NotteClient) -> Any:
        first = c.managed_auth.get_operation("op-1")
        clock[0] = 0.0
        with monkeypatch.context() as patch:
            patch.setattr("notte_sdk.endpoints.managed_auth.time.monotonic", tick)
            return c.managed_auth.wait_for_auth(first, timeout=4)

    async def async_call(c: AsyncNotteClient) -> Any:
        first = await c.managed_auth.get_operation("op-1")
        clock[0] = 0.0
        with monkeypatch.context() as patch:
            patch.setattr("notte_sdk.endpoints.managed_auth.time.monotonic", tick)
            return await c.managed_auth.wait_for_auth(first, timeout=4)

    exchange = await assert_same(monkeypatch, routes, sync_call, async_call)
    assert exchange.outcome[1] is TimeoutError


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "answer",
    [httpx.Response(200, json={"status": "ok"}), httpx.Response(503, json={}), httpx.ConnectError("refused")],
    ids=["ok", "unavailable", "unreachable"],
)
async def test_health_check_sends_the_same_request(monkeypatch: pytest.MonkeyPatch, answer: Any) -> None:
    routes: Routes = {("GET", "/health"): [answer]}

    async def async_call(c: AsyncNotteClient) -> None:
        await c.health_check()

    exchange = await assert_same(monkeypatch, routes, lambda c: c.health_check(), async_call)
    assert len(exchange.calls) == 1  # never retried
    assert "authorization" not in exchange.calls[0].headers
    assert exchange.outcome[0] == (
        "ok" if isinstance(answer, httpx.Response) and answer.status_code == 200 else "error"
    )


@pytest.mark.asyncio
async def test_concurrent_persona_and_vault_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    client = async_http_client()
    client._transport = httpx.MockTransport(Api({**PERSONA_ROUTES, **VAULT_ROUTES}))
    monkeypatch.setattr(AsyncSharedHttpClient, "get", lambda _: client)
    monkeypatch.setattr(SharedHttpClient, "get", no_sync_io)
    async with AsyncNotteClient(api_key=KEY, server_url=SERVER) as notte:
        persona, vault = await asyncio.gather(notte.Persona("persona-1"), notte.Vault("vault-1"))
        emails, sms, credentials, card = await asyncio.gather(
            persona.emails(), persona.sms(), vault.get_credentials("https://x.test"), vault.get_credit_card()
        )
    assert (emails[0].email_id, sms[0].sms_id) == ("e-1", "s-1")
    assert (normalize(credentials), card) == (CREDENTIALS, CARD)
    await client.aclose()
