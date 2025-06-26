import notte


def test_uploads(subtests):
    with notte.Storage(user_id="my_user_id") as storage, notte.Session(headless=False, storage=storage) as session:
        test_cases = [
            (
                "upload cat file, but do not send",
                "https://ps.uci.edu/~franklin/doc/file_upload.html",
                3,
                "cat_file_upload",
            ),
            ("upload image", "https://crop-circle.imageonline.co/", 3, "image_upload"),
            (
                "just upload the resume, don't do anything else",
                "https://apply.workable.com/huggingface/j/0BD8C06DB3/apply/",
                6,
                "resume_upload",
            ),
            (
                "upload the first txt file, do not submit or do anything else",
                "https://cloudconvert.com/txt-to-pdf",
                4,
                "txt_file_upload",
            ),
        ]

        for task, url, max_steps, description in test_cases:
            with subtests.test(description=description):
                agent = notte.Agent(
                    headless=False, session=session, reasoning_model="gemini/gemini-2.0-flash", max_steps=max_steps
                )
                resp = agent.run(url=url, task=task)
                assert resp.success
