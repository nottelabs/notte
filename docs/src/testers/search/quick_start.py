# @sniptest filename=search.py
import os

import requests

response = requests.post(
    "https://api.notte.cc/search",
    headers={"Authorization": f"Bearer {os.environ['NOTTE_API_KEY']}"},
    json={
        "q": "notte browser automation",
        "depth": "standard",
        "outputType": "searchResults",
    },
)
response.raise_for_status()
print(response.json())
