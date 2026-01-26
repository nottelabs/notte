# @sniptest filename=save_production_replays.py
# @sniptest show=8-15
import logging

from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    try:
        result = agent.run(task="Production task")
        if not result.success:
            replay = agent.replay()
            replay.save(f"prod_failure_{agent.agent_id}.mp4")
            logging.error(f"Agent failed, replay saved: prod_failure_{agent.agent_id}.mp4")
    except Exception as e:
        logging.error(f"Agent exception: {e}")
