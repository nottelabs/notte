# @sniptest filename=local_execution.py
from notte_sdk import NotteClient

client = NotteClient()

# Load the function (Notte-managed functions also need decryption_key="...")
function = client.Function(function_id="func_abc123")

# Runs on your machine
result = function.run(url="https://example.com", local=True)
