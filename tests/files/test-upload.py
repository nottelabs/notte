import notte


def test_uploads(subtests):
<<<<<<< HEAD
<<<<<<< HEAD
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

=======
    with notte.Session(
        headless=False,
    ) as session:
        dir = "tests/files"

=======
    with notte.Storage(user_id="my_user_id") as storage, notte.Session(headless=False, storage=storage) as session:
>>>>>>> dfde15e (Add Storage resource class and basic S3 integration)
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

>>>>>>> 2c8be7d (Improve upload file action, add download file action)
        for task, url, max_steps, description in test_cases:
            with subtests.test(description=description):
                agent = notte.Agent(
                    headless=False, session=session, reasoning_model="gemini/gemini-2.0-flash", max_steps=max_steps
                )
<<<<<<< HEAD
<<<<<<< HEAD
                resp = agent.run(url=url, task=task)
=======
                resp = agent.run(url=url, task=task, upload_dir=dir)
>>>>>>> 2c8be7d (Improve upload file action, add download file action)
=======
                resp = agent.run(url=url, task=task)
>>>>>>> dfde15e (Add Storage resource class and basic S3 integration)
                assert resp.success
