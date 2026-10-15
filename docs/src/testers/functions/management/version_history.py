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

# Other runs create functions in the same account at the same time, so this run's function
# may not be on the first page: page through the full list until it shows up.
matched = [func for func in functions.items if func.function_id == os.environ["NOTTE_FUNCTION_ID"]]
page = 1
while not matched:
    batch = client.functions.list(page=page, page_size=100)
    matched = [func for func in batch.items if func.function_id == os.environ["NOTTE_FUNCTION_ID"]]
    if not batch.has_next:
        break
    page += 1
assert len(matched) == 1
assert matched[0].latest_version in matched[0].versions
results = [bool(matched[0].versions), matched[0].latest_version in matched[0].versions]
