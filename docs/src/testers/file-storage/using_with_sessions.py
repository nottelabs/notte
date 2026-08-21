# @sniptest filename=using_with_sessions.py
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    session.storage.upload("data.csv")
    session.execute(type="goto", url="https://example.com/import")

    # Upload using the upload_file action
    session.execute(type="upload_file", selector='input[type="file"]', file_path="data.csv")

    session.execute(type="click", selector="button.submit")

# Download any files
for file in session.storage.list(source="session_download").files:
    session.storage.download(file.id, local_dir="./results")
