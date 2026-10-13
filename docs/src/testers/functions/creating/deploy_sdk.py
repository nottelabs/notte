# @sniptest filename=deploy_sdk.py
# @sniptest show=1-9
from notte_sdk import NotteClient

client = NotteClient()

# Deploy function
function = client.Function(path="scraper_function.py", name="Website Scraper", description="Scrapes data from websites")

print(f"Function deployed: {function.function_id}")
print(f"Version: {function.response.latest_version}")

try:
    response = function.response
    result = function.run(url="https://example.com", stream=False)
    assert result.status == "closed"
    assert response.latest_version in response.versions
    results = [response.name, response.description, response.shared, result.result]
finally:
    function.delete()
