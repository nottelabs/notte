# @sniptest filename=notte_hermes.py
# @sniptest typecheck_only=true
from notte_sdk import NotteClient

client = NotteClient()
session = client.Session(
    proxies=True,
    solve_captchas=True,
    open_viewer=True,
)
session.start()

print(session.cdp_url())
input("Press Enter when you are finished with Hermes... ")
session.stop()
