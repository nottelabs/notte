# @sniptest filename=graceful_errors.py
try:
    result = function.run(url="https://example.com")
    process_result(result.result)
except FailedToRunCloudFunctionError as e:
    log_error(e)
    send_alert(e.message)
