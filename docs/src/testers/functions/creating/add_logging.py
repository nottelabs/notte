# @sniptest filename=add_logging.py
from loguru import logger
from notte_sdk import NotteClient


def run(url: str):
    logger.info(f"Starting scrape of {url}")

    client = NotteClient()
    with client.Session() as session:
        logger.info("Session created")
        session.execute(type="goto", url=url)
        logger.info("Page loaded")

        data = session.scrape()
        logger.info(f"Extracted {len(data)} items")

    return data
