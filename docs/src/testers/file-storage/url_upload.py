# @sniptest filename=url_upload.py
# @sniptest show=1-11
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://test-resources-lovat.vercel.app/upload_fixture.html")
    session.execute(
        type="upload_file",
        selector='input[type="file"]',
        file_path="https://test-resources-lovat.vercel.app/text1.txt",
    )
    page = session.page
    uploaded = page.locator('input[type="file"]').evaluate(
        "async input => ({name: input.files[0].name, text: await input.files[0].text()})"
    )
    from urllib.request import urlopen

    with urlopen("https://test-resources-lovat.vercel.app/text1.txt", timeout=30) as response:
        assert uploaded == {"name": "text1.txt", "text": response.read().decode()}
    status = session.status()
