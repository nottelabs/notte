from unittest.mock import MagicMock

from notte_core.actions import CaptchaSolveAction
from notte_sdk.endpoints.page import CAPTCHA_SOLVE_REQUEST_TIMEOUT_SECONDS, PageClient


def test_captcha_solve_uses_150_second_request_timeout() -> None:
    client = PageClient.__new__(PageClient)
    client.request = MagicMock(return_value=MagicMock())

    client.execute("session-id", CaptchaSolveAction(captcha_type="recaptcha"))

    assert CAPTCHA_SOLVE_REQUEST_TIMEOUT_SECONDS == 150
    assert client.request.call_args.kwargs["timeout"] == CAPTCHA_SOLVE_REQUEST_TIMEOUT_SECONDS
