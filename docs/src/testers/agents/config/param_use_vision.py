# @sniptest filename=param_use_vision.py
# @sniptest show=6-9
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(
        session=session,
        use_vision=True,  # Agent can understand images
    )
