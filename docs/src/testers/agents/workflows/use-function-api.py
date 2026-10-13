# @sniptest filename=use-function-api.py
# @sniptest show=6-14
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    agent.run(task="Complete task")

    # Create function from successful agent
    function = agent.workflow.create_function()

    # Run it again whenever you need (it replays the agent's steps)
    for _ in range(3):
        result = function.run()
        print(result.result)
