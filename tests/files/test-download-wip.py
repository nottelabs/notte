import os

import notte

with notte.Session(
    headless=False,
) as session:
    url = "https://unsplash.com/photos/lined-of-white-and-blue-concrete-buildings-HadloobmnQs"
    task = "download the image, do nothing else"

    url = "https://crop-circle.imageonline.co/"
    task = "Upload the cat image and crop it to have a cirle border then download the new image, make sure to close any popups and avoid clicking on advertisements"
    udir = "tests/files"
    ddir = "tests/files/downloads"

    url = "https://archive.org/download/GeorgeOrwells1984"
    task = "download the pdf, do nothing else"

    url = "https://github.com/nottelabs/notte/blob/main/examples/README.md"
    task = "download the file (the raw button is NOT equivalent to download), do nothing else"

    agent = notte.Agent(headless=False, session=session, reasoning_model="gemini/gemini-2.5-flash", max_steps=3)
    resp = agent.run(url=url, task=task, upload_dir=udir, download_dir=ddir)

    print(resp.answer)

    i = 1
    replay_base_name = "image_upload_download-"
    replay_ext = ".webp"

    while os.path.exists(f"{replay_base_name}{str(i)}{replay_ext}"):
        i += 1

    resp.replay().save(f"{replay_base_name}{str(i)}{replay_ext}")
