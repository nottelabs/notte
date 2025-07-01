import os

import notte

url = "https://blueimp.github.io/jQuery-File-Upload/"

with (
    notte.Storage(upload_dir="tests/files", download_dir="tests/files/dwn") as storage,
    notte.Session(storage=storage, headless=False) as session,
):
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
    # url = "https://www.adobe.com/express/feature/image/convert/jpg-to-png"
    # url = "https://cloudconvert.com/txt-to-pdf"
    url = "https://crop-circle.imageonline.co/"

    # url = 'https://output.jsbin.com/hiqasek'
    # url = 'https://mburakerman.github.io/file-system-access-api-demo/'

    # url = 'https://support.lambdalabs.com/hc/en-us/requests/new?ticket_form_id=15831275190925'
    # url = "https://www.textcompare.org"

    task = "upload the image file, do not submit or do anything else"
    file = "tests/files/cat.jpg"  # resume.pdf" #text1.txt"
    # task = "upload the txt files to the support ticket, do not submit or do anything else"
    # task = "upload the pdf, do not submit or do anything else"

    # task = "upload the first txt as the original file and the second as the modified file and compare them"
    # task = "upload file and do nothing else"
    # dir = "tests/files"

    # obs = session.observe(url=url)
    # print(obs.space.markdown)

    agent = notte.Agent(session=session, reasoning_model="gemini/gemini-2.5-flash", max_steps=3)
    resp = agent.run(url=url, task=task)

    # task = ""
    # resp = agent.run(url=session.window.url, task=task, upload_dir=dir)

    print(resp.answer)

    i = 7
    replay_base_name = "image_upload-"
    replay_ext = ".webp"

    while os.path.exists(f"{replay_base_name}{str(i)}{replay_ext}"):
        i += 1

    # resp.replay().save(f"{replay_base_name}{str(i)}{replay_ext}")
