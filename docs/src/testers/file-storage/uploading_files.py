# @sniptest filename=uploading_files.py
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    session.storage.upload("report.pdf")
    session.storage.upload("report.pdf", upload_file_name="quarterly_report.pdf")
    print(session.storage.list(source="user_upload").files)
