# @sniptest filename=agent_retry.py
import time

from notte_sdk import NotteClient

client = NotteClient()

MAX_RETRIES = 3

for attempt in range(MAX_RETRIES):
    with client.Session() as session:
        agent = client.Agent(session=session)
        result = agent.run(task="Complete task")

        if result.success:
            print(f"Success: {result.answer}")
            break

        print(f"Attempt {attempt + 1} failed, retrying...")
        time.sleep(2**attempt)  # Exponential backoff
else:
    raise RuntimeError("Agent failed after all retries")
