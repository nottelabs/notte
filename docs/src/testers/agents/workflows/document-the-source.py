# @sniptest filename=document-the-source.py
# @sniptest show=8-18
from datetime import datetime

from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Extract product data")

    function = agent.workflow.create_function()

    # Add metadata
    metadata = {
        "agent_id": agent.agent_id,
        "original_task": "Extract product data",
        "created_at": datetime.now().isoformat(),
        "success_rate": result.success,
    }
