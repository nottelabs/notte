# @sniptest filename=version_history.py
from notte_sdk import NotteClient

client = NotteClient()

workflows = client.functions.list()

for workflow in workflows.workflows:
    print(f"Function: {workflow.name}")
    print(f"Versions: {', '.join(workflow.versions)}")
    print(f"Latest: {workflow.latest_version}")
