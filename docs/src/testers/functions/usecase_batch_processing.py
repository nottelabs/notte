# @sniptest filename=bulk_data_extract.py
from concurrent.futures import ThreadPoolExecutor

from notte_sdk import NotteClient


# bulk_data_extract.py
def run(urls: list[str], max_workers: int = 5):
    client = NotteClient()

    def extract_from_url(url):
        with client.Session() as session:
            session.execute(type="goto", url=url)
            data = session.scrape()
            return {"url": url, "data": data}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(extract_from_url, urls))

    return results
