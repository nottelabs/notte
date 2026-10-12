# @sniptest filename=add-error-handling.py
# @sniptest show=10-31
import textwrap

from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    agent.run(task="Complete task")

# Steps only (no imports, client or session boilerplate)
steps = agent.workflow.code(as_workflow=False).python_script

enhanced_code = f"""
from loguru import logger
from notte_sdk import NotteClient


def run():
    client = NotteClient()
    try:
        with client.Session() as session:
{textwrap.indent(steps, " " * 12)}
        return {{"success": True}}
    except Exception as e:
        logger.error(f"Function failed: {{e}}")
        return {{"success": False, "error": str(e)}}
"""

with open("function_with_error_handling.py", "w") as f:
    f.write(enhanced_code)
