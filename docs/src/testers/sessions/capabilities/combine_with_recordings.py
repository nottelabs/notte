# @sniptest filename=combine_with_recordings.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session(open_viewer=True) as session:
    # Watch it live
    session.execute(type="goto", url="https://example.com")
    session.execute(type="click", selector="button.submit")

# Get recording after session ends
replay = session.replay()
replay.save("recording.mp4")
