import notte

url = "https://blueimp.github.io/jQuery-File-Upload/"

with notte.Session(
    headless=False,
) as session:
    """
    url = 'https://www.textcompare.org/'
    task = 'upload the modified file, do nothing else'
    file = 'tests/files/text2.txt'

    agent = notte.Agent(headless=False, session=session, reasoning_model="gemini/gemini-2.0-flash", auto_manage_session=False, max_steps=6)
    resp = agent.run(url=url, task=task, file_path=file)

    task = 'upload the original file, do nothing else'
    file = 'tests/files/text1.txt'

    resp = agent.run(task=task, file_path=file)
    print(resp.answer)
    """

    # url = "https://favicon.io/favicon-converter/"
    # url = "https://practice.expandtesting.com/upload"
    # url = "https://www.w3docs.com/tools/code-editor/6963"
    # url = "https://www.adobe.com/acrobat/online/compress-pdf.html"
    url = "https://cloudconvert.com/txt-to-pdf"

    task = "upload the file, do not submit or do anything else"
    file = "tests/files/text1.txt"

    obs = session.observe(url=url)
    print(obs.space.markdown)

    agent = notte.Agent(headless=False, session=session, reasoning_model="gemini/gemini-2.0-flash", max_steps=3)
    resp = agent.run(url=url, task=task, file_path=file)

    print(resp.answer)
    resp.replay().save("image_upload-5.webp")


def test_simple_uploads():
    with notte.Session(
        headless=False,
    ) as session:
        task = "upload file, but do not send"
        file = "tests/files/cat.jpg"
        url = "https://ps.uci.edu/~franklin/doc/file_upload.html"

        agent = notte.Agent(headless=False, session=session, reasoning_model="gemini/gemini-2.0-flash", max_steps=3)
        resp = agent.run(url=url, task=task, file_path=file)
        assert resp.success

        task = "upload image"
        file = "tests/files/cat.jpg"
        url = "https://crop-circle.imageonline.co/"

        agent = notte.Agent(headless=False, session=session, reasoning_model="gemini/gemini-2.0-flash", max_steps=3)
        resp = agent.run(url=url, task=task, file_path=file)
        assert resp.success

        task = "upload resume"
        file = "tests/files/resume.pdf"
        url = "https://www.tesla.com/careers/search/job/apply/225833"  # update with any tesla job apply page if this one has been taken down

        agent = notte.Agent(headless=False, session=session, reasoning_model="gemini/gemini-2.0-flash", max_steps=4)
        resp = agent.run(url=url, task=task, file_path=file)
        assert resp.success
