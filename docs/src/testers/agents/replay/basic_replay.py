from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Navigate and extract data")

    # Get MP4 replay
    replay = agent.replay()

    # Display in notebook
    replay.show()

    # Or save to file
    replay.save("agent_run.mp4")
