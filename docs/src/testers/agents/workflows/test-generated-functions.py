# @sniptest filename=test-generated-functions.py
# @sniptest show=6-13
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    agent.run(task="Complete task")

    # Generate function code
    code = agent.workflow.code()

# Test in fresh session
with client.Session() as session:
    exec(code.python_script)
    # Verify it works
