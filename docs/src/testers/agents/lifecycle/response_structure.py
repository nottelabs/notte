# @sniptest filename=response_structure.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Extract data")

    # Access result properties
    print(result.success)  # bool: Did agent succeed?
    print(result.answer)  # str: Agent's response
    print(result.steps)  # list: All steps taken
    print(result.agent_id)  # str: Unique agent ID
    print(result.session_id)  # str: Session used
