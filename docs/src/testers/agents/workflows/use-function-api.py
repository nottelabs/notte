# @sniptest filename=use-function-api.py
# @sniptest show=6-12
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    agent.run(task="Complete task")

    # Create function from successful agent
    function = agent.workflow.create_function()

    # Run multiple times
    for query in ["laptop", "phone", "tablet"]:
        result = function.run(query=query)
        print(result)
