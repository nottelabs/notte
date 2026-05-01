# @sniptest filename=test_locally.py


# Define your function (from your scraper_function.py)
def run(url: str, selector: str) -> dict:
    # Your scraping logic here
    return {"url": url, "selector": selector}


# Test with sample parameters
result = run(url="https://example.com", selector=".content")

print(result)
