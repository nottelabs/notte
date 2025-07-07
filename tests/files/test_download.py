import pytest
from notte_sdk import NotteClient
from pydantic import BaseModel


class DownloadTest(BaseModel):
    url: str
    task: str
    description: str


unsplash_test = DownloadTest(
    url="https://unsplash.com/photos/lined-of-white-and-blue-concrete-buildings-HadloobmnQs",
    task="download the image, do nothing else",
    description="image download",
)


@pytest.mark.parametrize("test", [unsplash_test], ids=lambda x: x.description)
def test_file_storage_downloads(test: DownloadTest):
    notte = NotteClient()
    storage = notte.FileStorage()

    with notte.Session(storage=storage) as session:
        agent = notte.Agent(session=session, max_steps=3)
        resp = agent.run(url=test.url, task=test.task)

        assert resp.success

        downloaded_files = storage.list()
        assert len(downloaded_files) == 1, f"Expected 1 downloaded files, but found {len(downloaded_files)}"
