# @sniptest filename=add-parameters.py
# @sniptest show=8-15
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    agent.run(task="Complete task")

    # Agent-generated base code
    code = agent.workflow.code()

    # Customize with parameters
    customized_code = f"""
def extract_products(search_query: str, max_results: int = 10):
    {code.python_script}
"""
