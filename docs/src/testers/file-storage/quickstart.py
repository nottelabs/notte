# @sniptest filename=quickstart.py
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    # Every file belongs to this session.
    session.storage.upload("document.pdf")

    session.execute(type="goto", url="https://example.com/upload")
    session.execute(type="upload_file", selector='input[type="file"]', file_path="document.pdf")
    session.execute(type="download_file", selector="a.receipt")

# Download the files the session retrieved
for file in session.storage.list("session_download").files:
    session.storage.download(file.id, local_dir="./downloads")
