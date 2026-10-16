# @sniptest filename=scroll_down.py
# @sniptest show=1-18
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    # Create a page tall enough to scroll.
    session.evaluate_js(
        """(() => {
            document.open();
            document.write('<!doctype html><main>Scroll demo</main>');
            document.close();
            document.body.style.margin = '0';
            document.querySelector('main').style.height = '300vh';
            return document.documentElement.scrollHeight;
        })()"""
    )
    session.execute(type="scroll_down")
    print("Moved down: " + session.evaluate_js("String(window.scrollY > 0)"))

status = session.status()
