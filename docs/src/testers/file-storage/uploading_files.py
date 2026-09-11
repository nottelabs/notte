# @sniptest filename=uploading_files.py
# @sniptest show=3-9
from pathlib import Path

from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    session.storage.upload("report.pdf")
    session.storage.upload("report.pdf", upload_file_name="quarterly_report.pdf")
    print(session.storage.list(source="user_upload").files)
    status = session.status()

files = session.storage.list(source="user_upload").files
try:
    assert sorted(file.filename for file in files) == ["quarterly_report.pdf", "report.pdf"]
    for file in files:
        downloaded = session.storage.download(file.id, local_dir="./verified")
        assert Path(downloaded).read_bytes() == Path("report.pdf").read_bytes()
finally:
    for file in files:
        session.storage.delete(file.id)
