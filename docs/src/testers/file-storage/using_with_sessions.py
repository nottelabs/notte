# @sniptest filename=using_with_sessions.py
from notte_sdk import NotteClient

client = NotteClient()
storage = client.FileStorage()

# Upload file
storage.upload("data.csv")

with client.Session(storage=storage) as session:
    session.execute(type="goto", url="https://example.com/import")

    # Upload using the upload_file action
    session.execute(type="upload_file", selector='input[type="file"]', file_path="data.csv")

    session.execute(type="click", selector="button.submit")

# Download any files
for file_name in storage.list_downloaded_files():
    storage.download(file_name=file_name, local_dir="./results")
