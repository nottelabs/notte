# Manual run to figure out the task
agent = client.Agent(session=session)
result = agent.run(task="Extract daily price changes")

# Convert to function
function = agent.workflow.create()

# Schedule to run daily (via API or console)
# function.schedule(cron="0 9 * * *")
