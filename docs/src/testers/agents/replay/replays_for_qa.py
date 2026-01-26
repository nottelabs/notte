# @sniptest filename=replays_for_qa.py
# @sniptest show=6-16
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    # Test run
    result = agent.run(task="Test checkout flow")

    # Review replay before production
    replay = agent.replay()
    replay.save("qa_replay.mp4")

    # Verify:
    # - All steps completed correctly
    # - No unexpected behavior
    # - Performance is acceptable
