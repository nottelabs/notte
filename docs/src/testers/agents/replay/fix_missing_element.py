# @sniptest filename=fix_missing_element.py
# @sniptest show=8-15
import time

from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(session=session)
    # Be more specific in task
    task = "Wait for the page to load, then click the blue 'Submit' button at the bottom"

    # Or use session actions first
    session.execute(type="goto", url="https://example.com")
    time.sleep(2)  # Wait for load
    result = agent.run(task="Click submit button")
