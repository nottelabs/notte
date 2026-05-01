# @sniptest filename=pass_values.py
# @sniptest show=5
from notte_sdk import NotteClient

client = NotteClient()
function = client.Function(function_id="func_abc123")
function.run(email="user@example.com", password="secret", product_id="123")
