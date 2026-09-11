# @sniptest filename=attach_before_starting.py
# @sniptest show=18-24
from pathlib import Path

from notte_sdk.endpoints.files import RemoteFileStorage

# Record each successful upload before any subsequent request can fail.
owned_uploads = []
original_upload = RemoteFileStorage.upload


def tracked_upload(self, *args, **kwargs):
    uploaded = original_upload(self, *args, **kwargs)
    owned_uploads.append((self, uploaded.id))
    return uploaded


RemoteFileStorage.upload = tracked_upload
try:
    from notte_sdk import NotteClient

    client = NotteClient()

    with client.Session() as session:
        # Storage is always available and scoped to the session.
        session.storage.upload("file.pdf")
        assert session.status().status == "active"

    status = client.sessions.status(session.session_id)
    files = session.storage.list(source="user_upload").files
    assert sorted(file.filename for file in files) == ["file.pdf"]
    for file in files:
        downloaded = session.storage.download(file.id, local_dir="./verified")
        assert Path(downloaded).read_bytes() == Path("file.pdf").read_bytes()
finally:
    RemoteFileStorage.upload = original_upload
    cleanup_errors = []
    for storage, file_id in owned_uploads:
        try:
            storage.delete(file_id)
        except Exception as error:
            cleanup_errors.append(error)
    if cleanup_errors:
        raise ExceptionGroup("Failed to delete uploaded example files", cleanup_errors)
