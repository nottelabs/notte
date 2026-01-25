# @sniptest filename=using_with_agents.py
from notte_sdk import NotteClient

client = NotteClient()
storage = client.FileStorage()

# Upload files for the agent to use
storage.upload("contract.pdf")
storage.upload("signature.png")

with client.Session(storage=storage) as session:
    agent = client.Agent(session=session, max_steps=15)

    result = agent.run(
        task="""
        1. Upload contract.pdf to the document portal
        2. Add signature.png to the signature field
        3. Submit the form
        4. Download the signed confirmation
        """,
        url="https://example.com/documents",
    )

# Get the confirmation the agent downloaded
for file_name in storage.list_downloaded_files():
    storage.download(file_name=file_name, local_dir="./signed")
