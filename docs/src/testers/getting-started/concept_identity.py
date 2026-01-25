# @sniptest filename=concept_identity.py
# @sniptest show=4-5
from notte_sdk import NotteClient

client = NotteClient()
identity = client.identity.create()  # Generate synthetic identity
agent.run(task="Sign up for newsletter", identity=identity)
