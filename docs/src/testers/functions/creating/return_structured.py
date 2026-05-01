# @sniptest filename=return_structured.py
# @sniptest show=7-18
from datetime import datetime


def scrape_url(url: str) -> dict:
    return {"scraped": url}


def run(url: str):
    try:
        # Perform automation
        data = scrape_url(url)

        return {"success": True, "data": data, "url": url, "timestamp": datetime.now().isoformat()}

    except Exception as e:
        return {"success": False, "error": str(e), "url": url}
