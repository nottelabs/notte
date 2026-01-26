from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Complete task")

    print(f"Steps taken: {len(result.steps)}")
    print(f"Max steps: {agent.request.max_steps}")

    replay = agent.replay()
    replay.save("debug_replay.mp4")  # See where it got stuck
