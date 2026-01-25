# @sniptest filename=fork_function.py
from notte_sdk import NotteClient

client = NotteClient()

# Fork a function from marketplace or teammate
original = client.Function(function_id="func_abc123")
forked_function = original.fork()

print(f"Forked function ID: {forked_function.function_id}")
print("Original ID: func_abc123")
