# @sniptest filename=error_handling.py
def run():
    try:
        result = perform_automation()
        return {"success": True, "data": result}
    except Exception as e:
        # Log error, send alert
        return {"success": False, "error": str(e)}
