# @sniptest filename=access_replay.py
from notte_sdk import NotteClient

client = NotteClient()

function = client.Function(function_id="func_abc123")

# Run the function first
result = function.run(url="https://example.com")

# Get replay for this run (uses the session from the last run)
replay = function.replay()

# Save the replay
replay.save("function_replay.mp4")
