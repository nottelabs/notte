# @sniptest filename=list_functions.py
from notte_sdk import NotteClient

client = NotteClient()

# List all functions
functions = client.functions.list()

for func in functions.items:
    print(f"ID: {func.workflow_id}")
    print(f"Name: {func.name}")
    print(f"Version: {func.latest_version}")
    print(f"Created: {func.created_at}")
    print("---")
