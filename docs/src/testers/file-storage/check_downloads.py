# @sniptest filename=check_downloads.py
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    agent.run(task="Download all invoices")

# Check what was downloaded
files = session.storage.list("session_download").files
if not files:
    print("No files were downloaded")
else:
    for f in files:
        _ = session.storage.download(f.id, local_dir="./invoices")
