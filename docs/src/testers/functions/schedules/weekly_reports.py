# @sniptest filename=weekly_report.py
from datetime import datetime

from notte_sdk import NotteClient


def run():
    """Generate weekly report."""
    client = NotteClient()

    # Collect data from multiple sources
    report_data = []

    sources = ["https://analytics.example.com", "https://dashboard.example.com"]

    for url in sources:
        with client.Session() as session:
            session.execute(type="goto", url=url)
            data = session.scrape(instructions="Extract weekly metrics")
            report_data.append(data)

    return {"report": report_data, "week": datetime.now().isocalendar()[1]}
