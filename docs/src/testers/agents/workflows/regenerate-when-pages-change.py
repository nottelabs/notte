# @sniptest filename=regenerate-when-pages-change.py
# @sniptest show=7-19
from notte_sdk import NotteClient

client = NotteClient()
original_task_description = "Extract product data"
old_function = client.Function(function_id="func_old")

# Old function failing
try:
    old_function.run()
except Exception:
    print("Function broken, regenerating...")

    with client.Session() as session:
        # Use agent to figure out new function
        agent = client.Agent(session=session)
        result = agent.run(task=original_task_description)

        if result.success:
            # Generate new function
            new_function = agent.workflow.create_function()
            print(f"New function created: {new_function.function_id}")
