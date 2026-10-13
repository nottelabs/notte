# @sniptest filename=version_history.py
# @sniptest show=1-10
from notte_sdk import NotteClient

client = NotteClient()

functions = client.functions.list()

for func in functions.items:
    print(f"Function: {func.name}")
    print(f"Versions: {', '.join(func.versions)}")
    print(f"Latest: {func.latest_version}")

import os  # noqa: E402 -- hidden live assertions follow the displayed example

matched = [func for func in functions.items if func.function_id == os.environ["NOTTE_FUNCTION_ID"]]
assert len(matched) == 1
assert matched[0].latest_version in matched[0].versions
results = [bool(matched[0].versions), matched[0].latest_version in matched[0].versions]
