# @sniptest filename=uploading_files.py
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
        session.storage.upload("report.pdf")
        session.storage.upload("report.pdf", upload_file_name="quarterly_report.pdf")
        print(session.storage.list(source="user_upload").files)
        assert session.status().status == "active"

    status = client.sessions.status(session.session_id)
    files = session.storage.list(source="user_upload").files
    assert sorted(file.filename for file in files) == ["quarterly_report.pdf", "report.pdf"]
    for file in files:
        downloaded = session.storage.download(file.id, local_dir="./verified")
        assert Path(downloaded).read_bytes() == Path("report.pdf").read_bytes()
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
