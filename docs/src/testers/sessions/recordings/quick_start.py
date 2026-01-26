# @sniptest filename=quick_start.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://example.com")
    session.execute(type="click", selector="button.submit")
    session.execute(type="fill", selector="input[name='email']", value="user@example.com")
    # All actions automatically recorded

# Get replay after session ends
replay = session.replay()
replay.save("session_recording.mp4")
