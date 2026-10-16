# @sniptest filename=downloading_files.py
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    session.execute(type="goto", url="https://example.com/account")
    session.execute(type="download_file", selector="a.invoice")

# List downloaded files
downloaded = session.storage.list("session_download").files
print(f"Downloaded: {downloaded}")

# Download to local directory
for file in downloaded:
    session.storage.download(file.id, local_dir="./invoices")
