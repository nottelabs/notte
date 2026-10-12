from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Complete task")

    nb_steps = sum(1 for s in result.steps if s["type"] == "agent_step_start")
    print(f"Steps taken: {nb_steps}")
    print(f"Max steps: {agent.request.max_steps}")

replay = session.replay()
replay.download("debug_replay.mp4")  # See where it got stuck
