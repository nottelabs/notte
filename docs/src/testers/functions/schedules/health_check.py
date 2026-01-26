# @sniptest filename=weekly_health_check.py
from notte_sdk import NotteClient


def run():
    """Check if all schedules are healthy."""
    client = NotteClient()

    # Get all workflow runs from last 24 hours
    workflows = client.functions.list()

    health_report = []
    for workflow in workflows.items:
        runs = client.functions.list_runs(workflow.workflow_id)

        # Check recent runs
        recent_failures = [r for r in runs.items if r.status == "failed"]

        health_report.append({"workflow_id": workflow.workflow_id, "recent_failures": len(recent_failures)})

    return health_report
