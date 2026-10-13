# @sniptest filename=make_public.py
from notte_sdk import NotteClient

client = NotteClient()

# Deploy as shared
function = client.Function(
    path="my_function.py",
    name="Public Scraper",
    shared=True,  # Other users can view and fork it
)
