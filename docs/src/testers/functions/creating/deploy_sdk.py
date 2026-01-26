# @sniptest filename=deploy_sdk.py
from notte_sdk import NotteClient

client = NotteClient()

# Deploy function
function = client.Function(
    path="scraper_function.py", name="Website Scraper", description="Scrapes data from websites"
)

print(f"Function deployed: {function.function_id}")
print(f"Version: {function.response.latest_version}")
