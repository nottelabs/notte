# @sniptest filename=create-function-object.py
# @sniptest show=6-16
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Extract product data")

    if result.success:
        # Create function from agent
        function = agent.workflow.create_function()

        print(f"Created function: {function.function_id}")

        # Run function later
        function_result = function.run()
