# @sniptest filename=scroll_up.py
# @sniptest show=1-9
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    # Create a page tall enough to scroll.
    session.evaluate_js("document.body.innerHTML = '<main style=\"height:300vh\">Scroll demo</main>'")
    session.execute(type="scroll_down")
    session.execute(type="scroll_up")

status = session.status()
