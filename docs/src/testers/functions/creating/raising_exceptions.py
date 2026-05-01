# @sniptest filename=raising_exceptions.py
def run(url: str):
    if not url.startswith("https://"):
        raise ValueError("URL must use HTTPS")

    # Continue with automation
