# @sniptest filename=form_submission.py
from notte_sdk import NotteClient


def run(form_url: str, name: str, email: str, message: str):
    """Submit a contact form."""
    client = NotteClient()

    with client.Session() as session:
        session.execute(type="goto", url=form_url)
        session.execute(type="fill", id="name", value=name)
        session.execute(type="fill", id="email", value=email)
        session.execute(type="fill", id="message", value=message)
        session.execute(type="click", selector="button[type='submit']")

    return {"status": "submitted"}
