# @sniptest filename=graceful_errors.py
# @sniptest show=13-19
from notte_sdk import NotteClient

client = NotteClient()
function = client.Function(function_id="func_abc123")


def process_result(result: str) -> None:
    print(result)


def log_error(e: Exception) -> None:
    print(e)


def send_alert(message: str) -> None:
    print(message)


try:
    result = function.run(url="https://example.com")
    process_result(result.result)
except Exception as e:
    log_error(e)
    send_alert(str(e))
