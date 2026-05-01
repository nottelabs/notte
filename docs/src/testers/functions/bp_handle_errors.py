# @sniptest filename=bp_handle_errors.py
from notte_sdk import NotteClient


def run(url: str):
    try:
        client = NotteClient()
        with client.Session() as session:
            session.execute(type="goto", url=url)
            data = session.scrape()
            return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e), "error_type": type(e).__name__}
