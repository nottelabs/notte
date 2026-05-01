# @sniptest filename=validate_inputs.py
def run(url: str, count: int):
    # Validate inputs
    if not url.startswith("http"):
        return {"error": "Invalid URL format"}

    if count < 1 or count > 100:
        return {"error": "Count must be between 1 and 100"}

    # Proceed with automation
    pass
