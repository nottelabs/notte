# @sniptest filename=downloading_files.py
from notte_sdk import NotteClient

client = NotteClient()
storage = client.FileStorage()

with client.Session(storage=storage) as session:
    agent = client.Agent(session=session)
    agent.run(task="Download the invoice from the account page")

# List downloaded files
downloaded = storage.list_downloaded_files()
print(f"Downloaded: {downloaded}")

# Download to local directory
for file_name in downloaded:
    storage.download(file_name=file_name, local_dir="./invoices")
