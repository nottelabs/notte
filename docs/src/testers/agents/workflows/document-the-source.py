# @sniptest filename=document-the-source.py
# @sniptest show=9-25
import json
from datetime import datetime

from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Extract product data")

    function = agent.workflow.create_function()

    # Keep a record of where the function came from (e.g. in your repo)
    metadata = {
        "function_id": function.function_id,
        "agent_id": agent.agent_id,
        "original_task": "Extract product data",
        "created_at": datetime.now().isoformat(),
        "agent_success": result.success,
    }
    with open(f"function_{function.function_id}.json", "w") as f:
        json.dump(metadata, f, indent=2)
