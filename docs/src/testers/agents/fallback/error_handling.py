# @sniptest filename=error_handling.py
# @sniptest show=7-18
from loguru import logger
from notte_sdk import NotteClient

client = NotteClient()


def alert_failure(message: str) -> None:
    logger.error(message)


try:
    with client.Session() as session:
        with client.AgentFallback(session, task="Critical task") as fb:
            session.execute(type="click", selector="#button")

        if not fb.success:
            # Even agent couldn't complete the task
            alert_failure(f"Task failed: {fb.steps[-1].message}")
except Exception as e:
    # Unexpected error
    logger.error(f"Fallback exception: {e}")
