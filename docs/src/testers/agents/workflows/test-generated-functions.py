# @sniptest filename=test-generated-functions.py
# @sniptest show=6-15
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    agent.run(task="Complete task")

    # Generate function code
    code = agent.workflow.code()

# Save for review before testing in a fresh session
with open("generated_function.py", "w", encoding="utf-8") as generated_file:
    generated_file.write(code.python_script)

print("Saved generated_function.py. Review it before running it in an isolated environment.")
