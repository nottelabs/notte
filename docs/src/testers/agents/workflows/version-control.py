# @sniptest filename=version-control.py
# @sniptest show=7-14
from pathlib import Path

from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    agent.run(task="Extract products")

    # Save function code
    code = agent.workflow.code()

    function_path = Path("functions/extract_products.py")
    function_path.parent.mkdir(exist_ok=True)
    function_path.write_text(code.python_script)

# Commit to git
# git add functions/extract_products.py
# git commit -m "Add product extraction function from agent run"
