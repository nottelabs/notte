# @sniptest filename=save_to_file.py
# @sniptest show=8-15
from pathlib import Path

from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    agent.run(task="Complete task")

    replay = agent.replay()
    replay.save("debug_run.mp4")

    # With custom path
    output_dir = Path("./replays")
    output_dir.mkdir(exist_ok=True)
    replay.save(str(output_dir / f"agent_{agent.agent_id}.mp4"))
