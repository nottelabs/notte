import os

import notte

# upload_dir="tests/files", download_dir="tests/files/dwn"
with notte.Storage(user_id="my_user_id") as storage, notte.Session(storage=storage, headless=False) as session:
    # url = "https://unsplash.com/photos/lined-of-white-and-blue-concrete-buildings-HadloobmnQs"
    # task = "download the image, do nothing else"

    url = "https://crop-circle.imageonline.co/"
    task = "Upload the cat image and crop it to have a cirle border then download the new image, make sure to close any popups and avoid clicking on or close advertisements that are in the way"
    # udir = "tests/files"
    # ddir = "tests/files/downloads"

    # url = "https://archive.org/download/GeorgeOrwells1984"
    # task = "download the pdf, do nothing else"

    # url = "https://github.com/nottelabs/notte/blob/main/examples/README.md"
    # task = "download the file (the raw button is NOT equivalent to download), do nothing else"

    agent = notte.Agent(session=session, reasoning_model="gemini/gemini-2.5-flash", max_steps=10)
    resp = agent.run(url=url, task=task)

    print(resp.answer)

    i = 1
    replay_base_name = "image_upload-download-"
    replay_ext = ".webp"

    while os.path.exists(f"{replay_base_name}{str(i)}{replay_ext}"):
        i += 1

    resp.replay().save(f"{replay_base_name}{str(i)}{replay_ext}")
