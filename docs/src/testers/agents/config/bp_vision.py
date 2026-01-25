# @sniptest filename=bp_vision.py
# Text-only site
agent = client.Agent(session=session, use_vision=False)

# Image-heavy site
agent = client.Agent(session=session, use_vision=True)
