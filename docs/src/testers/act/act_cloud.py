# @sniptest filename=act_cloud.py
# @sniptest typecheck_only=true
from notte_sdk import NotteClient

client = NotteClient()

# act() runs in your process, on top of observe() and execute(): bring your own decider key
with client.Session() as session:
    _ = session.execute(type="goto", url="https://en.wikipedia.org/wiki/Main_Page")
    result = session.act("search for Ada Lovelace")
    print(result.status, result.operation, result.target, result.value)
