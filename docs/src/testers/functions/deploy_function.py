# @sniptest filename=deploy_function.py
from notte_sdk import NotteClient

client = NotteClient()

# Deploy function
function = client.Function(
    path="my_automation.py", name="Search Automation", description="Searches a website and extracts results"
)

print(f"Function deployed: {function.function_id}")
print(f"Version: {function.response.latest_version}")
