# @sniptest filename=select_element.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    # Select the first "Transactions" element
    session.execute(type="click", selector="text=Transactions >> nth=0")
