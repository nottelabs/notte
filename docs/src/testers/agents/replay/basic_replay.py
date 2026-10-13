from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Navigate and extract data")

# Get MP4 replay (returns presigned URL)
replay = session.replay()
print(replay.mp4_url)  # Presigned URL for MP4 download

# Download to file
replay.download("agent_run.mp4")
