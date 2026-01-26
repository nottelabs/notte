from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(session=session)

    # Successful run
    result_success = agent.run(task="Working task")
    replay_success = agent.replay()
    replay_success.save("success.mp4")

    # Failed run
    result_fail = agent.run(task="Failing task")
    replay_fail = agent.replay()
    replay_fail.save("failure.mp4")

    # Compare side-by-side
    # Identify where behavior diverges
