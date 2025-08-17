import notte


def run():
    url = "https://shop.notte.cc/"
    with notte.Session(headless=True, perception_type="fast") as session:
        session.execute({"type": "goto", "url": url})
        session.observe()
        resp = session.scrape()
        _ = notte.Agent(session=session, max_steps=3).run(
            task="goto goole.com, search for 'notte agents' and click on the first result"
        )
    return resp
