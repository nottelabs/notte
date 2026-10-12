# @sniptest filename=download_code.py
from notte_sdk import NotteClient

client = NotteClient()

# Notte-managed functions also need decryption_key="..."
function = client.Function(function_id="func_abc123")

# Download function code
code = function.download()

print(code)  # Function source code

# Or download directly to a file
code = function.download(path="downloaded_function.py")
