# Agent-generated base code
code = agent.workflow.code()

# Customize with parameters
customized_code = f"""
def extract_products(search_query: str, max_results: int = 10):
    {code.python_script}
"""
