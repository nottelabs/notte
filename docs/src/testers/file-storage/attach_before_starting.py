# @sniptest filename=attach_before_starting.py
# @sniptest show=3-9
from pathlib import Path

from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    # Storage is always available and scoped to the session.
    session.storage.upload("file.pdf")
    status = session.status()

files = session.storage.list(source="user_upload").files
try:
    assert [file.filename for file in files] == ["file.pdf"]
    downloaded = session.storage.download(files[0].id, local_dir="./verified")
    assert Path(downloaded).read_bytes() == Path("file.pdf").read_bytes()
finally:
    for file in files:
        session.storage.delete(file.id)
