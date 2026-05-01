from notte_sdk import NotteClient

client = NotteClient()
fallback_invoked_count = 0
total_runs = 0

for _ in range(100):
    with client.Session() as session:
        with client.AgentFallback(session, task="Task") as fb:
            session.execute(type="click", selector="#button")

    total_runs += 1
    if fb.agent_invoked:
        fallback_invoked_count += 1

fallback_rate = fallback_invoked_count / total_runs
print(f"Agent fallback rate: {fallback_rate:.1%}")

# If rate is high, consider:
# - Updating selectors
# - Using agents directly
# - Improving page stability
