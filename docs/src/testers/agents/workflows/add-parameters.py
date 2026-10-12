# @sniptest filename=add-parameters.py
# @sniptest show=1-26
import textwrap

from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    agent.run(task="Complete task")

# Steps only (no imports, client or session boilerplate)
steps = agent.workflow.code(as_workflow=False).python_script

# Wrap the steps in a parameterized function
customized_code = f"""
from notte_sdk import NotteClient


def run(search_query: str, max_results: int = 10):
    client = NotteClient()
    with client.Session() as session:
{textwrap.indent(steps, " " * 8)}
"""

# Edit the steps to use search_query and max_results, then save
with open("extract_products.py", "w") as f:
    f.write(customized_code)
