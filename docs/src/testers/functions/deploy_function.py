# @sniptest filename=deploy_function.py
# @sniptest show=1-11
from notte_sdk import NotteClient

client = NotteClient()

# Deploy function
function = client.Function(
    path="my_automation.py", name="Search Automation", description="Searches a website and extracts results"
)

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
