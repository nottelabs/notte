# @sniptest filename=error_handling.py
# @sniptest show=7-24
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
            # Even the agent couldn't complete the task
            if fb.agent_response is not None:
                alert_failure(f"Agent failed: {fb.agent_response.answer}")
            else:
                alert_failure("Task failed before the agent was invoked")
except Exception as e:
    # Unexpected error
    logger.error(f"Fallback exception: {e}")
