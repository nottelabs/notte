# @sniptest filename=bp_return_structured.py
from datetime import datetime


def my_function():
    results = []  # your data

    # Good - return JSON-serializable dict
    return {"success": True, "data": results, "count": len(results), "timestamp": datetime.now().isoformat()}

    # Bad - not JSON serializable
    # return datetime.now()  # Can't serialize datetime directly
