from pathlib import Path

import pytest
from notte_sdk import NotteClient
from pydantic import BaseModel

DATA_DIR = Path(__file__).parent / "data"


class UploadTest(BaseModel):
    task: str
    url: str
    description: str
    max_steps: int


file_upload_tests = [
    UploadTest(
        task="upload cat file, but do not send",
        url="https://ps.uci.edu/~franklin/doc/file_upload.html",
        max_steps=3,
        description="cat_file_upload",
    ),
    UploadTest(
        task="upload cat image",
        url="https://crop-circle.imageonline.co/",
        max_steps=4,
        description="image_upload",
    ),
    UploadTest(
        task="upload the first txt file, do not submit or do anything else",
        url="https://cloudconvert.com/txt-to-pdf",
        max_steps=4,
        description="txt_file_upload",
    ),
]


@pytest.mark.parametrize("test", file_upload_tests, ids=lambda x: x.description)
def test_uploads(test: UploadTest):
    notte = NotteClient()
    storage = notte.FileStorage()

    with notte.Session(storage=storage) as session:
        files = ["cat.jpg", "resume.pdf", "text1.txt"]

        for f in files:
            resp = storage.upload(str(DATA_DIR / f))
            assert resp.success

        uploaded = storage.list_uploaded_files()

        for f in files:
            assert f in uploaded

        agent = notte.Agent(session=session, max_steps=test.max_steps)
        resp = agent.run(url=test.url, task=test.task)
        assert resp.success


def test_upload_non_existent_file_should_raise_error():
    notte = NotteClient()
    storage = notte.FileStorage()

    with pytest.raises(FileNotFoundError):
        _ = storage.upload(str(DATA_DIR / "non_existent_file.txt"))
