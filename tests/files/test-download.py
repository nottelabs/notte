import notte


def test_downloads(subtests):
    with (
        notte.Storage(upload_dir="tests/files", download_dir="tests/files/dwn") as storage,
        notte.Session(headless=False, storage=storage) as session,
    ):
        tests = [
            (
                "https://unsplash.com/photos/lined-of-white-and-blue-concrete-buildings-HadloobmnQs",
                "download the image, do nothing else",
                "image download",
            )
        ]

        n_files = 0

        for url, task, description in tests:
            with subtests.test(description=description):
                agent = notte.Agent(session=session, reasoning_model="gemini/gemini-2.5-flash", max_steps=3)
                resp = agent.run(url=url, task=task)

                assert resp.success

                # TBD: update test assert to check number of files in S3 bucket
                # assert len([name for name in os.listdir(dir) if os.path.isfile(os.path.join(dir, name))]) == n_files + 1

                n_files += 1
