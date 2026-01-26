# @sniptest filename=download_file.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://example.com")
    result = session.execute(type="download_file", selector="a.download-link")
    print(f"Downloaded: {result}")
