from notte_sdk import NotteClient

client = NotteClient()

# Successful run
with client.Session() as session_1:
    agent_1 = client.Agent(session=session_1)
    result_success = agent_1.run(task="Working task")
replay_success = session_1.replay()
replay_success.download("success.mp4")

# Failed run
with client.Session() as session_2:
    agent_2 = client.Agent(session=session_2)
    result_fail = agent_2.run(task="Failing task")
replay_fail = session_2.replay()
replay_fail.download("failure.mp4")

# Compare side-by-side
# Identify where behavior diverges
