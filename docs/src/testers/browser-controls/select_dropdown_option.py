# @sniptest filename=select_dropdown_option.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://example.com")

    # Select by visible text
    session.execute(type="select_dropdown_option", selector="select#country", option_text="United States")

    # Select by value
    session.execute(type="select_dropdown_option", selector="select#country", option_value="us")
