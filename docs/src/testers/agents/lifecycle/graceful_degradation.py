# @sniptest filename=graceful_degradation.py
# @sniptest show=6-17
from loguru import logger
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Complete task")

    if result.success:
        # Process successful result
        print(result.answer)
    else:
        # Handle failure
        logger.error(f"Agent failed: {result.answer}")

        # Fallback strategy
        print("Executing fallback approach...")
