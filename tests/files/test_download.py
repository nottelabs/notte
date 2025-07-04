from notte_sdk import NotteClient


def test_downloads(subtests):
    notte = NotteClient()

    with notte.FileStorage() as storage, notte.Session(storage=storage) as session:
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

                downloaded_files = storage.list()
                assert len(downloaded_files) == n_files + 1, (
                    f"Expected {n_files + 1} downloaded files, but found {len(downloaded_files)}"
                )

                n_files += 1
