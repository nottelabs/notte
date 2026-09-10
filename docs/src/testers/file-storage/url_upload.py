# @sniptest filename=url_upload.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://example.com/upload")
    session.execute(
        type="upload_file",
        selector='input[type="file"]',
        file_path="https://example.com/document.pdf",
    )
