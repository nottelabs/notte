# @sniptest filename=step_by_step_analysis.py
# @sniptest show=6-21
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Complex task")

    for step in result.steps:
        value = step["value"]
        if step["type"] == "agent_completion":
            state = value["state"]
            print("\n=== Agent decision ===")
            print(f"Previous goal: {state['previous_goal_status']} - {state['previous_goal_eval']}")
            print(f"Next goal: {state['next_goal']}")
        elif step["type"] == "execution_result":
            action = value["action"]
            print(f"Action: {action['type']}")
            if action["type"] == "goto":
                print(f"URL: {action['url']}")
            print(f"Success: {value['success']}")
            print(f"Message: {value['message']}")
