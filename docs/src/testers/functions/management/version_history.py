# @sniptest filename=version_history.py
from notte_sdk import NotteClient

client = NotteClient()

functions = client.functions.list()

for func in functions.items:
    print(f"Function: {func.name}")
    print(f"Versions: {', '.join(func.versions)}")
    print(f"Latest: {func.latest_version}")
