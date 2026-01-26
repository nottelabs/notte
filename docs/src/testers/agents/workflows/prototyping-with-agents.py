# @sniptest filename=prototyping-with-agents.py
# @sniptest show=6-16
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    # Phase 1: Prototype with agent
    agent = client.Agent(session=session)
    result = agent.run(task="Find all products under $100")

    if result.success:
        # Phase 2: Convert to function for production
        code = agent.workflow.code()

        # Save for production use
        with open("production_function.py", "w") as f:
            f.write(code.python_script)
