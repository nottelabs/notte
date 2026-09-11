from notte_sdk import NotteClient

client = NotteClient()


def run(url: str):
    with client.Session() as session:
        session.execute(type="goto", url=url)
        return session.scrape()
