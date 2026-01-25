# @sniptest filename=css_selectors.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://example.com")

    # By ID
    session.execute(type="click", selector="#submit-button")

    # By class
    session.execute(type="click", selector=".btn-primary")

    # By attribute
    session.execute(type="click", selector="button[type='submit']")

    # By combination
    session.execute(type="click", selector="form#login button.submit")

    # By nth-child
    session.execute(type="click", selector="ul li:nth-child(2)")
