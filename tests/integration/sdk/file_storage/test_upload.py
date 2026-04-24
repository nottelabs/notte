from pathlib import Path

import pytest
from dotenv import load_dotenv
from notte_sdk import NotteClient
from pydantic import BaseModel

_ = load_dotenv()

DATA_DIR = Path(__file__).parent / "data"
UPLOAD_FIXTURE_URL = "https://test-resources-lovat.vercel.app/upload_fixture.html"


def test_upload_non_existent_file_should_raise_error():
    notte = NotteClient()
    storage = notte.FileStorage()

    with pytest.raises(FileNotFoundError):
        _ = storage.upload(str(DATA_DIR / "non_existent_file.txt"))


class FixtureUploadCase(BaseModel):
    file_name: str
    expected_mime: str
    # Lowercase hex of the first 16 bytes of the file.
    expected_hex_prefix: str


fixture_upload_cases = [
    FixtureUploadCase(
        file_name="text1.txt",
        expected_mime="text/plain",
        expected_hex_prefix="6f726967696e616c2066696c65210a74",  # pragma: allowlist secret
    ),
    FixtureUploadCase(
        file_name="cat.jpg",
        expected_mime="image/jpeg",
        expected_hex_prefix="ffd8ffe000104a464946000102010048",  # pragma: allowlist secret
    ),
    FixtureUploadCase(
        file_name="resume.pdf",
        expected_mime="application/pdf",
        expected_hex_prefix="255044462d312e360d25e2e3cfd30d0a",  # pragma: allowlist secret
    ),
]


@pytest.mark.parametrize("case", fixture_upload_cases, ids=lambda c: c.file_name)
def test_upload_against_local_fixture(case: FixtureUploadCase):
    """Agent-less upload test against a self-hosted HTML fixture.

    The fixture at UPLOAD_FIXTURE_URL renders the uploaded file's name,
    MIME type, size, and first bytes after the Validate button is clicked,
    so we can assert an upload actually reached the page.
    """
    notte = NotteClient()
    storage = notte.FileStorage()

    with notte.Session(storage=storage) as session:
        assert storage.upload(str(DATA_DIR / case.file_name))

        _ = session.execute(type="goto", url=UPLOAD_FIXTURE_URL)
        _ = session.execute(type="upload_file", selector="#file-input", file_path=case.file_name)
        _ = session.execute(type="click", selector="#validate-btn")

        content = session.scrape()

        assert "NO_FILE_SELECTED" not in content, "fixture reported no file was selected"
        assert case.file_name in content, f"expected filename {case.file_name!r} in scraped page"
        assert case.expected_mime in content, f"expected MIME {case.expected_mime!r} in scraped page"
        assert case.expected_hex_prefix in content, (
            f"expected first-bytes hex {case.expected_hex_prefix!r} in scraped page"
        )
