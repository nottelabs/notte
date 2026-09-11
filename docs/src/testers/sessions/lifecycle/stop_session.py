# @sniptest filename=stop_session.py
# @sniptest show=5-13
from notte_sdk import NotteClient

client = NotteClient()

session = client.Session()
session.start()
try:
    status = session.status()
    if status.status != "active":
        raise RuntimeError("Session is not active")
finally:
    session.stop()
print("Session stopped successfully")
