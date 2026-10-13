# @sniptest filename=list_functions.py
from notte_sdk import NotteClient

client = NotteClient()

# List functions (one page: 10 per page by default)
functions = client.functions.list(page_size=50)

for func in functions.items:
    print(f"ID: {func.function_id}")
    print(f"Name: {func.name}")
    print(f"Version: {func.latest_version}")
    print(f"Created: {func.created_at}")
    print("---")
