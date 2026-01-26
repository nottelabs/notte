# @sniptest filename=backup_functions.py
import os

from notte_sdk import NotteClient

client = NotteClient()

functions = client.functions.list()

# Create backup directory
os.makedirs("function_backups", exist_ok=True)

for func in functions.items:
    function = client.Function(function_id=func.workflow_id, decryption_key="your-key")

    try:
        code = function.download()

        filename = f"function_backups/{func.name}_{func.latest_version}.py"
        with open(filename, "w") as f:
            f.write(code)

        print(f"Backed up: {func.name}")
    except Exception as e:
        print(f"Failed to backup {func.name}: {e}")
