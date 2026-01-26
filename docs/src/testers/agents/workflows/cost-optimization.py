# @sniptest filename=cost-optimization.py
# @sniptest show=6-15
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    # One-time: Use agent to solve the task ($0.20)
    agent = client.Agent(session=session)
    result = agent.run(task="Complex data extraction")

    # Recurring: Use function ($0.05 per run)
    function = agent.workflow.create_function()

    # Run 100 times - save $15 vs running agent each time
    for i in range(100):
        function.run()
