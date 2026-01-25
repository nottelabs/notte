# @sniptest filename=concept_observation.py
# @sniptest show=4
from notte_sdk import NotteClient

client = NotteClient()
session = client.Session()
obs = session.observe()  # Get structured page analysis
