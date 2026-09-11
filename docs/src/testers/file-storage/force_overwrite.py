# @sniptest filename=force_overwrite.py
# @sniptest show=15-19
from pathlib import Path

from notte_sdk import NotteClient as FixtureClient

fixture = FixtureClient()
with fixture.Session() as session:
    uploaded = session.storage.upload("file.pdf")
    try:
        session_id = session.session_id
        file_id = uploaded.id
        destination = Path("downloads/file.pdf")
        destination.parent.mkdir()
        destination.write_bytes(b"old contents")

        from notte_sdk import NotteClient

        client = NotteClient()
        storage = client.FileStorage(session_id)
        storage.download(file_id, local_dir="./downloads", force=True)

        assert destination.read_bytes() == Path("file.pdf").read_bytes()
        status = session.status()
    finally:
        session.storage.delete(uploaded.id)
