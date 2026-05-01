# @sniptest filename=add-error-handling.py
# @sniptest show=8-22
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    agent.run(task="Complete task")

    # Agent-generated code
    base_code = agent.workflow.code()

    enhanced_code = f"""
from notte_sdk import NotteClient
from loguru import logger

def run_function():
    client = NotteClient()
    try:
        with client.Session() as session:
            {base_code.python_script}
            return {{"success": True, "data": result}}
    except Exception as e:
        logger.error(f"Function failed: {{e}}")
        return {{"success": False, "error": str(e)}}
"""
