# @sniptest filename=match_viewport.py
# @sniptest show=1-11
from notte_sdk import NotteClient

client = NotteClient()

# Desktop
with client.Session(viewport_width=1920, viewport_height=1080) as desktop:
    pass

# Laptop
with client.Session(viewport_width=1366, viewport_height=768) as session:
    pass

status = session.status()
assert status.viewport_width == 1366
assert status.viewport_height == 768
desktop_status = desktop.status()
assert desktop_status.viewport_width == 1920
assert desktop_status.viewport_height == 1080
results = [desktop_status.session_id, status.session_id]
