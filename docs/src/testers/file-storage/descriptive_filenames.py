# @sniptest filename=descriptive_filenames.py
from datetime import datetime

from notte_sdk import NotteClient

client = NotteClient()
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
with client.Session() as session:
    session.storage.upload("report.pdf", upload_file_name=f"report_{timestamp}.pdf")
