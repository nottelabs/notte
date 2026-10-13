# @sniptest filename=using_with_agents.py
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    session.storage.upload("contract.pdf")
    session.storage.upload("signature.png")
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
for file in session.storage.list(source="session_download").files:
    session.storage.download(file.id, local_dir="./signed")
