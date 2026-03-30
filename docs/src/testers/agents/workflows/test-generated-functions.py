# @sniptest filename=test-generated-functions.py
# @sniptest show=6-17
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    agent.run(task="Complete task")

    # Generate function code
    code = agent.workflow.code()

# Save for review before testing in a fresh session
with open("generated_function.py", "w") as generated_file:
    generated_file.write(code.python_script)

print("Saved generated_function.py. Review the code before running it in a fresh session.")
