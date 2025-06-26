import notte


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

        task = "just upload the resume, don't do anything else"
        file = "tests/files/resume.pdf"
        url = "https://www.tesla.com/careers/search/job/apply/225833"  # update with any tesla job apply page if this one has been taken down

        agent = notte.Agent(headless=False, session=session, reasoning_model="gemini/gemini-2.0-flash", max_steps=3)
        resp = agent.run(url=url, task=task, file_path=file)
        assert resp.success
