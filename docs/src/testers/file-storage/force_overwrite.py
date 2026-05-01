# @sniptest filename=force_overwrite.py
from notte_sdk import NotteClient

client = NotteClient()
storage = client.FileStorage()

storage.download(
    file_name="report.pdf",
    local_dir="./downloads",
    force=True,  # Overwrite if exists
)
