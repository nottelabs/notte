from pathlib import Path

replay = agent.replay()
replay.save("debug_run.mp4")

# With custom path
output_dir = Path("./replays")
output_dir.mkdir(exist_ok=True)
replay.save(output_dir / f"agent_{agent.agent_id}.mp4")
