# @sniptest filename=linkedin_step.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as page:
    url = "https://www.linkedin.com/"

    # observe page and take a step
    page.execute(type="goto", url=url)
    actions = page.observe(instructions="click 'jobs'")
    res = page.execute(actions[0])
    print(res.message)

    # another one
    actions = page.observe(instructions="dismiss the sign in check")
    res = page.execute(actions[0])
    print(res.message)
