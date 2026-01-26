# @sniptest filename=file_upload_download.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://example.com/upload")

    # Upload file
    session.execute(type="upload_file", selector="input[type='file']", file_path="/path/to/document.pdf")
    session.execute(type="click", selector="button.submit")

    # Wait for processing
    session.execute(type="wait", time_ms=3000)

    # Download result
    result = session.execute(type="download_file", selector="a.download")
    print(f"Downloaded: {result}")
