# @sniptest filename=private_function.py
from notte_sdk import NotteClient

client = NotteClient()

function = client.Function(
    path="my_function.py",
    name="Private Automation",
    shared=False,  # Private (default)
)
