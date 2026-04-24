import tempfile
from pathlib import Path

import pytest
from dotenv import load_dotenv
from notte_browser.errors import NoStorageObjectProvidedError
from notte_core.actions import DownloadFileAction
from notte_sdk import NotteClient
from pydantic import BaseModel, Field

import notte

_ = load_dotenv()

DATA_DIR = Path(__file__).parent / "data"
FIXTURE_HOST = "https://test-resources-lovat.vercel.app"


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


@pytest.mark.flaky(reruns=3, reruns_delay=2)
@pytest.mark.parametrize("test", [unsplash_test, arxiv_test], ids=lambda x: x.description)
def test_file_storage_downloads(test: DownloadTest):
    notte = NotteClient()
    storage = notte.FileStorage()

    with notte.Session(storage=storage) as session:
        agent = notte.Agent(session=session, max_steps=test.max_steps)
        _ = agent.run(url=test.url, task=test.task)

        # assert resp.success

        downloaded_files = storage.list_downloaded_files()
        assert len(downloaded_files) == 1, f"Expected 1 downloaded files, but found {len(downloaded_files)}"

        # try to dowwload the file
        with tempfile.TemporaryDirectory() as tmp_dir:
            success = storage.download(file_name=downloaded_files[0].name, local_dir=tmp_dir)
            assert success
            assert Path(tmp_dir).exists()


def test_download_file_action_fails_no_storage():
    with notte.Session() as session:
        _ = session.execute(type="goto", url="https://arxiv.org/pdf/1706.03762")
        obs = session.observe()
        print(obs.space.description)
        action = DownloadFileAction(id="I0")
        with pytest.raises(NoStorageObjectProvidedError):
            _ = session.execute(action)


class FixtureDownloadCase(BaseModel):
    description: str
    url: str
    selector: str
    # Storage prepends a timestamp (e.g. "2026_04_24_00_54_44-resume.pdf"), so
    # we compare with endswith rather than equality.
    expected_filename_suffix: str
    expected_bytes: bytes = Field(repr=False)


def _local_bytes(name: str) -> bytes:
    return (DATA_DIR / name).read_bytes()


fixture_download_cases = [
    FixtureDownloadCase(
        # Note: Vercel serves static assets with Content-Disposition:
        # inline; filename="text1.txt", and Chromium uses that header's
        # filename as the suggested filename, overriding the anchor's
        # download="downloaded_link.txt" attribute. We assert content
        # integrity; the exact filename here is infra-controlled.
        description="anchor_download_attr",
        url=f"{FIXTURE_HOST}/download_link.html",
        selector="#dl-link",
        expected_filename_suffix="text1.txt",
        expected_bytes=_local_bytes("text1.txt"),
    ),
    FixtureDownloadCase(
        description="blob_button",
        url=f"{FIXTURE_HOST}/download_blob.html",
        selector="#dl-btn",
        expected_filename_suffix="blob_payload.txt",
        expected_bytes=b"blob fixture payload\n",
    ),
    FixtureDownloadCase(
        description="raw_txt",
        url=f"{FIXTURE_HOST}/text1.txt",
        selector="body",
        expected_filename_suffix="text1.txt",
        expected_bytes=_local_bytes("text1.txt"),
    ),
    FixtureDownloadCase(
        description="raw_jpg",
        url=f"{FIXTURE_HOST}/cat.jpg",
        selector="body",
        expected_filename_suffix="cat.jpg",
        expected_bytes=_local_bytes("cat.jpg"),
    ),
    FixtureDownloadCase(
        description="raw_pdf",
        url=f"{FIXTURE_HOST}/resume.pdf",
        selector="body",
        expected_filename_suffix="resume.pdf",
        expected_bytes=_local_bytes("resume.pdf"),
    ),
]


@pytest.mark.parametrize("case", fixture_download_cases, ids=lambda c: c.description)
def test_download_against_local_fixture(case: FixtureDownloadCase):
    """Agent-less download test against self-hosted fixtures.

    Covers three code paths in the download controller:
    - click-to-download on an <a download> (anchor path)
    - click-to-download on a button that synthesizes a blob URL (non-<a> path)
    - navigating directly to a raw asset and using selector="body"
      (window.is_file() path)

    For each case we also download the file back locally and assert the bytes
    match byte-for-byte.
    """
    notte = NotteClient()
    storage = notte.FileStorage()

    with notte.Session(storage=storage) as session:
        _ = session.execute(type="goto", url=case.url)
        _ = session.execute(type="download_file", selector=case.selector)

        downloaded = storage.list_downloaded_files()
        names = [f.name for f in downloaded]
        matching = [n for n in names if n.endswith(case.expected_filename_suffix)]
        assert len(matching) == 1, (
            f"expected exactly one file ending with {case.expected_filename_suffix!r}, got {names}"
        )
        stored_name = matching[0]

        with tempfile.TemporaryDirectory() as tmp_dir:
            assert storage.download(file_name=stored_name, local_dir=tmp_dir)
            local_path = Path(tmp_dir) / stored_name
            assert local_path.exists(), f"{local_path} missing after storage.download"
            assert local_path.read_bytes() == case.expected_bytes, f"byte mismatch for {stored_name}"
