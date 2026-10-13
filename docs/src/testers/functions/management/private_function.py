# @sniptest filename=private_function.py
# @sniptest show=1-9
from notte_sdk import NotteClient

client = NotteClient()

function = client.Function(
    path="my_function.py",
    name="Private Automation",
    shared=False,  # Private (default)
)

try:
    response = function.response
    result = function.run(url="https://example.com", stream=False)
    assert result.status == "closed"
    assert response.latest_version in response.versions
    results = [response.name, response.description, response.shared, result.result]
finally:
    function.delete()
