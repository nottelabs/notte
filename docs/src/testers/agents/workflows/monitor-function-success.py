# @sniptest filename=monitor-function-success.py
from datetime import datetime

from loguru import logger
from notte_sdk import NotteClient

client = NotteClient()


def run_monitored_function():
    function = client.Function(function_id="func_abc123")
    # raise_on_failure=False returns failed runs instead of raising
    result = function.run(raise_on_failure=False)

    if result.status == "closed":
        logger.info(f"Function succeeded at {datetime.now()}")
    else:
        # Function broken - maybe the page changed?
        # Time to re-run the agent and regenerate
        logger.error(f"Function failed: {result.result}")
