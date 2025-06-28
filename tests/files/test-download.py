<<<<<<< HEAD
<<<<<<< HEAD
=======
import os
import tempfile

>>>>>>> 2c8be7d (Improve upload file action, add download file action)
=======
>>>>>>> dfde15e (Add Storage resource class and basic S3 integration)
import notte


def test_downloads(subtests):
<<<<<<< HEAD
<<<<<<< HEAD
    with notte.Storage(user_id="my_user_id") as storage, notte.Session(headless=False, storage=storage) as session:
=======
    with notte.Session(headless=False) as session, tempfile.TemporaryDirectory() as dir:
>>>>>>> 2c8be7d (Improve upload file action, add download file action)
=======
    with notte.Storage(user_id="my_user_id") as storage, notte.Session(headless=False, storage=storage) as session:
>>>>>>> dfde15e (Add Storage resource class and basic S3 integration)
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
                agent = notte.Agent(
                    headless=False, session=session, reasoning_model="gemini/gemini-2.5-flash", max_steps=3
                )
<<<<<<< HEAD
<<<<<<< HEAD
                resp = agent.run(url=url, task=task)

                assert resp.success

                # TBD: update test assert to check number of files in S3 bucket
                # assert len([name for name in os.listdir(dir) if os.path.isfile(os.path.join(dir, name))]) == n_files + 1
=======
                resp = agent.run(url=url, task=task, download_dir=dir)

                assert resp.success
                assert len([name for name in os.listdir(dir) if os.path.isfile(os.path.join(dir, name))]) == n_files + 1
>>>>>>> 2c8be7d (Improve upload file action, add download file action)
=======
                resp = agent.run(url=url, task=task)

                assert resp.success

                # TBD: update test assert to check number of files in S3 bucket
                # assert len([name for name in os.listdir(dir) if os.path.isfile(os.path.join(dir, name))]) == n_files + 1
>>>>>>> dfde15e (Add Storage resource class and basic S3 integration)

                n_files += 1
