# @sniptest filename=bp_add_logging.py
from loguru import logger
from notte_sdk import NotteClient


def run(url: str):
    logger.info(f"Starting automation for {url}")

    client = NotteClient()
    with client.Session() as session:
        logger.info("Session started")
        session.execute(type="goto", url=url)
        logger.info("Navigation complete")

        data = session.scrape()
        logger.info(f"Extracted {len(data)} items")

    return data
