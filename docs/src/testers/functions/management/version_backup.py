# @sniptest filename=version_backup.py
from notte_sdk import NotteClient

client = NotteClient()

function = client.Function(function_id="func_abc123")

# Before major update, download current version
current_code = function.download(decryption_key="key")

# Save backup
with open(f"backups/function_v{function.response.latest_version}.py", "w") as f:
    f.write(current_code)

# Update function
function.update(path="new_version.py")
