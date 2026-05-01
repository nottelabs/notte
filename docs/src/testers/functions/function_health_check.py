# @sniptest filename=function_health_check.py
from notte_sdk import NotteClient

client = NotteClient()


def check_function_health(function_id: str):
    """Check recent run success rate."""
    runs = client.functions.list_runs(function_id, only_active=False)

    total = len(runs.items)
    failed = sum(1 for r in runs.items if r.status == "failed")

    success_rate = ((total - failed) / total * 100) if total > 0 else 0

    print(f"Success rate: {success_rate:.1f}%")
    print(f"Total runs: {total}")
    print(f"Failed runs: {failed}")

    return success_rate


# Monitor function
check_function_health("func_abc123")
