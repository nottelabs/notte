# @sniptest filename=deployment_options.py
from notte_sdk import NotteClient

client = NotteClient()

function = client.Function(
    path="my_function.py",
    name="My Function",  # Display name
    description="What this function does",  # Description
    shared=False,  # Private by default
)
