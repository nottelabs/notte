from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Complete task")

replay = session.replay()
replay.download("missing_element.mp4")

# Watch replay and check:
# - Did page finish loading?
# - Is element visible/in viewport?
# - Is element covered by another element?
