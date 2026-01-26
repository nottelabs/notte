# @sniptest filename=creating_agent.py
# @sniptest show=6-14
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(
        session=session,
        reasoning_model="gemini/gemini-2.0-flash",
        use_vision=True,
        max_steps=15,
        # vault=vault,  # Optional
        # persona=persona,  # Optional
    )
