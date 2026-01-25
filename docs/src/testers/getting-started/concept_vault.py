# @sniptest filename=concept_vault.py
# @sniptest show=4-5
from notte_sdk import NotteClient

client = NotteClient()
client.vault.store("github", {"username": "...", "password": "..."})
agent.run(task="Login to GitHub", vault="github")
