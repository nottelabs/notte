import tempfile
from pathlib import Path

import pytest
from notte_sdk import NotteClient
from pydantic import BaseModel


class DownloadTest(BaseModel):
    url: str
    task: str
    description: str
    max_steps: int


unsplash_test = DownloadTest(
    url="https://unsplash.com/photos/lined-of-white-and-blue-concrete-buildings-HadloobmnQs",
    task="download the image, do nothing else",
    description="image_download",
    max_steps=4,
)


@pytest.mark.parametrize("test", [unsplash_test], ids=lambda x: x.description)
def test_file_storage_downloads(test: DownloadTest):
    notte = NotteClient()
    storage = notte.FileStorage()

    with notte.Session(storage=storage) as session:
        agent = notte.Agent(session=session, max_steps=test.max_steps)
        resp = agent.run(url=test.url, task=test.task)

        assert resp.success

        downloaded_files = storage.list_downloaded_files()
        assert len(downloaded_files) == 1, f"Expected 1 downloaded files, but found {len(downloaded_files)}"

        # try to dowwload the file
        with tempfile.TemporaryDirectory() as tmp_dir:
            success = storage.download(file_name=downloaded_files[0], local_dir=tmp_dir)
            assert success
            assert Path(tmp_dir).exists()
