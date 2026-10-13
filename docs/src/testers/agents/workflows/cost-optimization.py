# @sniptest filename=cost-optimization.py
# @sniptest show=6-15
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    # One-time: use an agent to solve the task (LLM reasoning on every step)
    agent = client.Agent(session=session)
    result = agent.run(task="Complex data extraction")

    # Recurring: replay the steps as a function (no LLM reasoning)
    function = agent.workflow.create_function()

    # Run it as often as you need
    for i in range(100):
        function.run()
