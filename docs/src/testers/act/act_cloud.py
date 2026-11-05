# @sniptest filename=act_cloud.py
# @sniptest typecheck_only=true
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    _ = session.execute(type="goto", url="https://en.wikipedia.org/wiki/Main_Page")

    # one step, decided and run by the API
    result = session.act("type Ada Lovelace in the search box")
    print(result.status, result.action, result.confidence)

    # variables are filled in after the model call: their values never reach a model
    proposed = session.act("type {{query}} in the search box", variables={"query": "Alan Turing"}, dry_run=True)
    print(proposed.action)

    choice = session.choose("What kind of page is this?", ["encyclopedia", "online shop", "login page"])
    if session.check("Is there a search box?") > 0.8:
        print(choice.choice)
