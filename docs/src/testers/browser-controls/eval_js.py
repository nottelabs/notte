# @sniptest filename=eval_js.py
import json

from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://notte.cc/")
    # evaluate_js returns the evaluated string; failures raise with the JS error
    title = session.evaluate_js("document.title")
    # objects and arrays come back as JSON
    links = json.loads(session.evaluate_js("Array.from(document.querySelectorAll('a')).map(a => a.href)"))
