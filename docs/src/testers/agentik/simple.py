# @sniptest show=1-7
# @sniptest highlight=5-7

from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    agent.run(task="go to google, and find cat pictures")

# === TESTING CODE BELOW (hidden from snippet via #@show) ===
if __name__ == "__main__":
    print("Running test...")
    # This allows the file to be tested with pytest or run directly
