# @sniptest filename=advanced_agent.py
# @sniptest icon=rocket
# @sniptest lines=true
# @sniptest expandable=true
# @sniptest highlight=5-7
# @sniptest show=1-10

from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="go to google, and find cat pictures")
    print(result)

# Hidden test code below
if __name__ == "__main__":
    print("Testing...")
