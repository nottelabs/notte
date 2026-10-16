# @sniptest filename=scroll_up.py
# @sniptest show=1-11
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    # Create a page tall enough to scroll.
    session.evaluate_js("document.body.innerHTML = '<main style=\"height:300vh\">Scroll demo</main>'")
    session.execute(type="scroll_down", selector="html")
    print("Moved down: " + session.evaluate_js("String(window.scrollY > 0)"))
    session.execute(type="scroll_up", selector="html")
    print("Returned to top: " + session.evaluate_js("String(window.scrollY === 0)"))

status = session.status()
