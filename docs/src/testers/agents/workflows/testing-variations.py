# @sniptest filename=testing-variations.py
# @sniptest show=6-14
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    # Base workflow from agent
    agent = client.Agent(session=session)
    result = agent.run(task="Search and extract results")

    code = agent.workflow.code()

    # Modify code for variations
    # - Different search queries
    # - Different extraction logic
    # - Different URLs
