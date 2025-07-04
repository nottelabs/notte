from notte_sdk import NotteClient


def test_uploads(subtests):
    notte = NotteClient()

    with notte.FileStorage() as storage, notte.Session(storage=storage) as session:
        files = ["cat.jpg", "resume.pdf", "text1.txt"]

        for f in files:
            storage.upload(f"tests/files/{f}")

        uploaded = storage.list(type="uploads")

        for f in files:
            assert f in uploaded

        test_cases = [
            (
                "upload cat file, but do not send",
                "https://ps.uci.edu/~franklin/doc/file_upload.html",
                3,
                "cat_file_upload",
            ),
            ("upload cat image", "https://crop-circle.imageonline.co/", 3, "image_upload"),
            (
                "upload the first txt file, do not submit or do anything else",
                "https://cloudconvert.com/txt-to-pdf",
                4,
                "txt_file_upload",
            ),
            # Unreliable test:
            # (
            #     "just upload the resume, don't do anything else",
            #     "https://apply.workable.com/huggingface/j/0BD8C06DB3/apply/",
            #     6,
            #     "resume_upload",
            # ),
        ]

        for task, url, max_steps, description in test_cases:
            with subtests.test(description=description):
                agent = notte.Agent(session=session, reasoning_model="gemini/gemini-2.5-flash", max_steps=max_steps)
                resp = agent.run(url=url, task=task)
                assert resp.success
