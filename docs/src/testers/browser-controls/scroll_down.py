# @sniptest filename=scroll_down.py
# @sniptest show=1-9
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    # Create a page tall enough to scroll.
    session.evaluate_js("document.body.innerHTML = '<main style=\"height:300vh\">Scroll demo</main>'")
    session.execute(type="scroll_down", selector="html")
    print("Moved down: " + session.evaluate_js("String(window.scrollY > 0)"))

status = session.status()
