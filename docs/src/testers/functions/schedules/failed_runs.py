# @sniptest filename=failed_runs.py
def run():
    try:
        # Your automation
        result = perform_automation()

        # Send success notification
        notify_success(result)

        return result

    except Exception as e:
        # Send failure alert
        notify_failure(str(e))

        # Return error info
        return {"success": False, "error": str(e)}
