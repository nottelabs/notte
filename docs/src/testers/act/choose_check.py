# @sniptest filename=choose_check.py
# @sniptest typecheck_only=true
import notte

with notte.Session() as session:
    _ = session.execute(type="goto", url="https://news.ycombinator.com")

    # pick one option about the current page, with a probability per option
    choice = session.choose("What kind of page is this?", ["news aggregator", "online shop", "login page"])
    print(choice.choice, choice.probabilities, choice.confidence)

    # options can carry descriptions
    choice = session.choose(
        "Is there a way to sign in?",
        {"link": "a login link is visible", "form": "a login form is visible", "none": "no way to sign in"},
    )

    # the probability that a yes/no question holds on the page
    if session.check("Is the user logged in?") < 0.5:
        print("not logged in")
