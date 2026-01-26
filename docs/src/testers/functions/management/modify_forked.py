# @sniptest filename=modify_forked.py
from notte_sdk import NotteClient

client = NotteClient()

# Fork function
original = client.Function(function_id="shared_function_id")
forked = original.fork()

# Update your copy
forked.update(path="my_modified_version.py")

# Run your version
result = forked.run(url="https://example.com")
