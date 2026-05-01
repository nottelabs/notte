# @sniptest filename=descriptive_filenames.py
from datetime import datetime

from notte_sdk import NotteClient

client = NotteClient()
storage = client.FileStorage()

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
storage.upload("report.pdf", upload_file_name=f"report_{timestamp}.pdf")
