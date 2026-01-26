# @sniptest filename=image_extraction.py
from notte_sdk import NotteClient

client = NotteClient()
images = client.scrape("https://example.com/gallery", only_images=True)

for image in images:
    print(f"URL: {image.url}")
    print(f"Description: {image.description}")
