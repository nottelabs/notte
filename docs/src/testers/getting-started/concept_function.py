# @sniptest filename=concept_function.py
# @sniptest show=4-5
from notte_sdk import NotteClient

client = NotteClient()
function = client.functions.deploy(name="scrape-product", code=my_script)
client.functions.invoke("scrape-product", params={"url": "https://..."})
