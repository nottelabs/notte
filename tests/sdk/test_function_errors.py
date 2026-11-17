"""Typed function errors: the classes users raise, the payload the runner reports, and rejected runs."""

import json
from typing import Any, ClassVar

import httpx
import pytest
from notte_core.errors import NotteBaseError
from notte_sdk import ExpectedFunctionError, FunctionError, NotteClient, RetryableFunctionError
from notte_sdk.endpoints.functions import FailedToRunCloudFunctionError, FunctionRunRejectedError
from notte_sdk.errors import function_error_payload
from notte_sdk.types import FunctionRunResponse, GetFunctionRunResponse

from tests.sdk.test_async_functions_files import Api, Flow, same_exchange, sse
from tests.sdk.test_async_functions_files import run_routes as base_routes
from tests.sdk.test_async_resources import exchange_sync


class AccountNotUnique(ValueError, ExpectedFunctionError):
    status_code = 409


class StaffMustReview(ExpectedFunctionError):
    code = "needs_staff_review"


class SiteDown(RetryableFunctionError):
    pass


class HTTPTimeout(RetryableFunctionError):
    pass


class HealableRefusal(ExpectedFunctionError):
    heal = True


class Plain(FunctionError):
    pass


def raised(exc: BaseException) -> BaseException:
    """The exception as the runner sees it: raised and caught, with a traceback."""
    try:
        raise exc
    except BaseException as caught:
        return caught


# ---------------------------------------------------------------------------
# Classes


def test_presets_have_the_contract_defaults() -> None:
    assert (FunctionError.heal, FunctionError.retry, FunctionError.status_code, FunctionError.code) == (
        True,
        False,
        500,
        None,
    )
    assert (ExpectedFunctionError.heal, ExpectedFunctionError.retry, ExpectedFunctionError.status_code) == (
        False,
        False,
        422,
    )
    assert (RetryableFunctionError.heal, RetryableFunctionError.retry, RetryableFunctionError.status_code) == (
        False,
        True,
        503,
    )


def test_function_errors_are_plain_exceptions_not_api_errors() -> None:
    assert FunctionError.__mro__[1] is Exception
    assert not issubclass(FunctionError, NotteBaseError)


def test_multiple_inheritance_keeps_builtin_handlers_working() -> None:
    with pytest.raises(ValueError, match="2 accounts"):
        raise AccountNotUnique("2 accounts match")
    with pytest.raises(ExpectedFunctionError):
        raise AccountNotUnique("2 accounts match")
    assert AccountNotUnique.status_code == 409
    assert AccountNotUnique.heal is False


# ---------------------------------------------------------------------------
# Payload


@pytest.mark.parametrize(
    "cls,code",
    [
        (AccountNotUnique, "account_not_unique"),
        (SiteDown, "site_down"),
        (HTTPTimeout, "http_timeout"),
        (Plain, "plain"),
        (ValueError, "value_error"),
        (KeyError, "key_error"),
        (StaffMustReview, "needs_staff_review"),
    ],
)
def test_code_defaults_to_snake_case_class_name(cls: type[BaseException], code: str) -> None:
    assert function_error_payload(raised(cls("x")))["code"] == code


def test_expected_payload() -> None:
    assert function_error_payload(raised(AccountNotUnique("2 accounts match"))) == {
        "kind": "expected",
        "type": "AccountNotUnique",
        "mro": [
            "AccountNotUnique",
            "ValueError",
            "ExpectedFunctionError",
            "FunctionError",
            "Exception",
            "BaseException",
        ],
        "code": "account_not_unique",
        "message": "2 accounts match",
        "heal": False,
        "retry": False,
        "status_code": 409,
        "source": "class",
    }


def test_retryable_payload() -> None:
    payload = function_error_payload(raised(SiteDown("503 from the portal")))
    assert {k: payload[k] for k in ("kind", "code", "heal", "retry", "status_code", "source")} == {
        "kind": "retryable",
        "code": "site_down",
        "heal": False,
        "retry": True,
        "status_code": 503,
        "source": "class",
    }


def test_plain_function_error_is_unexpected_with_class_source() -> None:
    payload = function_error_payload(raised(Plain("boom")))
    assert (payload["kind"], payload["heal"], payload["retry"], payload["status_code"], payload["source"]) == (
        "unexpected",
        True,
        False,
        500,
        "class",
    )


@pytest.mark.parametrize("exc", [RuntimeError("boom"), KeyboardInterrupt()])
def test_other_exceptions_are_unexpected_defaults(exc: BaseException) -> None:
    payload = function_error_payload(raised(exc))
    name = type(exc).__name__
    assert payload == {
        "kind": "unexpected",
        "type": name,
        "mro": [klass.__name__ for klass in type(exc).__mro__ if klass is not object],
        "code": "runtime_error" if name == "RuntimeError" else "keyboard_interrupt",
        "message": str(exc),
        "heal": True,
        "retry": False,
        "status_code": 500,
        "source": "default",
    }


def test_overrides_report_actual_attributes_and_keep_the_preset_kind() -> None:
    payload = function_error_payload(raised(HealableRefusal("x")))
    assert (payload["kind"], payload["heal"], payload["retry"], payload["status_code"]) == (
        "expected",
        True,
        False,
        422,
    )

    class NoRetry(RetryableFunctionError):
        retry = False
        status_code = 502

    payload = function_error_payload(raised(NoRetry("x")))
    assert (payload["kind"], payload["heal"], payload["retry"], payload["status_code"]) == (
        "retryable",
        False,
        False,
        502,
    )


def test_kind_follows_the_nearest_preset_in_the_mro() -> None:
    class Both(RetryableFunctionError, ExpectedFunctionError):
        pass

    payload = function_error_payload(raised(Both("x")))
    assert payload["kind"] == "retryable"
    assert (payload["heal"], payload["retry"], payload["status_code"]) == (False, True, 503)


def test_payload_never_fails_on_bad_user_classes() -> None:
    class Unprintable(ExpectedFunctionError):
        status_code: ClassVar[Any] = "409"

        def __str__(self) -> str:
            raise RuntimeError("no")

    payload = function_error_payload(raised(Unprintable()))
    assert payload["message"] == "<unprintable Unprintable>"
    assert payload["status_code"] == 500
    assert payload["kind"] == "expected"
    json.dumps(payload)


# ---------------------------------------------------------------------------
# Wire models


def test_run_models_accept_rejected_and_error() -> None:
    error = function_error_payload(raised(AccountNotUnique("2 accounts match")))
    run = FunctionRunResponse.model_validate(
        {
            "function_id": "f",
            "function_run_id": "r",
            "session_id": None,
            "result": None,
            "status": "rejected",
            "error": error,
        }
    )
    assert run.status == "rejected" and run.error == error
    legacy = FunctionRunResponse.model_validate(
        {"function_id": "f", "function_run_id": "r", "session_id": None, "result": 1, "status": "closed"}
    )
    assert legacy.error is None
    stored = GetFunctionRunResponse.model_validate(
        {
            "function_id": "f",
            "function_run_id": "r",
            "created_at": "2026-11-16T00:00:00Z",
            "updated_at": "2026-11-16T00:00:00Z",
            "status": "rejected",
            "error": error,
        }
    )
    assert stored.status == "rejected" and stored.error == error


# ---------------------------------------------------------------------------
# NotteFunction.run


ERROR = function_error_payload(raised(AccountNotUnique("2 accounts match")))


def rejected_routes(error: dict[str, Any] | None = ERROR) -> Any:
    routes = base_routes("rejected")
    result: dict[str, Any] = {"function_id": "f-1", "function_run_id": "r-1", "session_id": "s-9", "status": "rejected"}
    if error is not None:
        result["error"] = error

    def start(request: httpx.Request) -> Any:
        if not json.loads(request.content)["stream"]:
            return {**result, "result": None}
        return sse(
            {"type": "session_start", "message": "s-9"},
            {"type": "result", "message": json.dumps({**result, "result": None})},
        )

    routes[("POST", "/functions/f-1/runs/r-1")] = start
    return routes


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [True, False])
async def test_rejected_run_raises_rejected_error(monkeypatch: pytest.MonkeyPatch, stream: bool) -> None:
    async def flow(c: Any, wait: Any) -> Any:
        return await wait(c.Function("f-1").run(stream=stream))

    run: Flow = flow
    exchange = await same_exchange(monkeypatch, rejected_routes(), run)
    assert exchange.outcome[0] == "error"
    assert exchange.outcome[1] is FunctionRunRejectedError
    assert issubclass(exchange.outcome[1], FailedToRunCloudFunctionError)
    assert exchange.outcome[2] == "Function f-1 with run_id=r-1 was rejected (account_not_unique): 2 accounts match"


@pytest.mark.asyncio
async def test_rejected_run_is_returned_without_raise_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def flow(c: Any, wait: Any) -> Any:
        response = await wait(c.Function("f-1").run(raise_on_failure=False))
        return [response.status, response.error]

    run: Flow = flow
    exchange = await same_exchange(monkeypatch, rejected_routes(), run)
    assert exchange.outcome == ("ok", ["rejected", ERROR])


def test_rejected_error_carries_code_and_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    caught: list[FunctionRunRejectedError] = []

    def call(client: NotteClient) -> None:
        try:
            client.Function("f-1").run()
        except FailedToRunCloudFunctionError as error:  # existing handlers still catch it
            assert isinstance(error, FunctionRunRejectedError)
            caught.append(error)

    _ = exchange_sync(monkeypatch, Api(rejected_routes()), call)
    (error,) = caught
    assert error.code == "account_not_unique"
    assert error.error == ERROR
    assert error.response.status == "rejected"
    assert (error.function_id, error.function_run_id) == ("f-1", "r-1")
    assert error.message == "Function f-1 with run_id=r-1 was rejected (account_not_unique): 2 accounts match"


def test_rejected_run_without_error_payload_still_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    exchange = exchange_sync(monkeypatch, Api(rejected_routes(error=None)), lambda c: c.Function("f-1").run())
    assert exchange.outcome == (
        "error",
        FunctionRunRejectedError,
        "Function f-1 with run_id=r-1 was rejected: result 'None'",
    )


@pytest.mark.asyncio
async def test_failed_run_still_raises_the_base_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def flow(c: Any, wait: Any) -> Any:
        return await wait(c.Function("f-1").run())

    run: Flow = flow
    exchange = await same_exchange(monkeypatch, base_routes("failed"), run)
    assert exchange.outcome[:2] == ("error", FailedToRunCloudFunctionError)


def test_sdk_opts_in_to_the_rejected_run_status() -> None:
    # Without this header the API shows rejected runs as "failed" (old-SDK compatibility).
    client = NotteClient(api_key="test-key")
    assert client.functions.headers()["x-notte-accept-run-statuses"] == "rejected"
