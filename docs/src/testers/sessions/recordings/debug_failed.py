# @sniptest filename=debug_failed.py
from notte_sdk import NotteClient

client = NotteClient()

session_id = None

try:
    with client.Session() as session:
        session_id = session.session_id
        session.execute(type="goto", url="https://example.com")
        session.execute(type="click", selector="button.sometimes-missing")

except Exception as e:
    print(f"Automation failed: {e}")

    if session_id:
        # Get recording to see what happened
        replay = client.sessions.replay(session_id=session_id)
        replay.save(f"failed_{session_id}.mp4")
        print("Replay saved for analysis")
