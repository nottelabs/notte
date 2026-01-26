# @sniptest filename=get-python-script.py
# @sniptest show=6-13
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Login and navigate to dashboard")

    if result.success:
        # Get function code
        code = agent.workflow.code(as_workflow=True)

        print(code.python_script)
