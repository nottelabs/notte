import tempfile
from pathlib import Path

import pytest
from dotenv import load_dotenv
from notte_browser.errors import NoStorageObjectProvidedError
from notte_core.actions import DownloadFileAction
from notte_sdk import NotteClient
from pydantic import BaseModel

import notte

_ = load_dotenv()


class DownloadTest(BaseModel):
    url: str
    task: str
    description: str
    max_steps: int


unsplash_test = DownloadTest(
    url="https://unsplash.com/photos/lined-of-white-and-blue-concrete-buildings-HadloobmnQs",
    task="download the image, do nothing else",
    description="image_download",
    max_steps=5,
)


arxiv_test = DownloadTest(
    url="https://arxiv.org/abs/1706.03762",
    task="download the pdf, do nothing else",
    description="pdf_download",
    max_steps=5,
)


@pytest.mark.parametrize("test", [unsplash_test, arxiv_test], ids=lambda x: x.description)
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


def test_download_file_action_fails_no_storage():
    with notte.Session() as session:
        _ = session.execute({"type": "goto", "url": "https://arxiv.org/pdf/1706.03762"})
        obs = session.observe()
        print(obs.space.description)
        action = DownloadFileAction(id="I0")
        with pytest.raises(NoStorageObjectProvidedError):
            _ = session.execute(action)
