# @sniptest filename=attach_before_starting.py
from notte_sdk import NotteClient

client = NotteClient()

# Correct
storage = client.FileStorage()
storage.upload("file.pdf")

with client.Session(storage=storage) as session:
    # Storage is available
    pass
