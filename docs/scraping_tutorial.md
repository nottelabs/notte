# Web Scraping with Notte

Notte provides powerful tools for web scraping that can extract both raw content and structured data from web pages. This tutorial will guide you through the different ways you can use Notte for web scraping.

## Basic Web Scraping

The simplest way to scrape a webpage is to extract its content as markdown. This is useful when you want to preserve the page's structure and formatting.

```python
import os
from notte_sdk import NotteClient

client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
with client.Session() as page:
    data = page.scrape(url="https://www.notte.cc")
    print(data.markdown)
```

> [!NOTE]
> You can also use `NotteSession` from `notte_browser.session` to scrape webpages locally.

## Structured Data Extraction

For more sophisticated use cases, you can extract structured data from web pages by defining a schema using Pydantic models. This is particularly useful when you need to extract specific information like product details, pricing plans, or article metadata.

### Example: Extracting Pricing Plans

Let's say you want to extract pricing information from a website. First, define your data models then use these models to extract structured data:

```python
import os
from pydantic import BaseModel
from notte_sdk import NotteClient
from notte_browser.session import NotteSession

class PricingPlan(BaseModel):
    name: str
    price_per_month: int | None
    features: list[str]

class PricingPlans(BaseModel):
    plans: list[PricingPlan]

client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
with client.Session() as page:
    data = page.scrape(
        url="https://www.notte.cc",
        response_format=PricingPlans,
        instructions="Extract the pricing plans from the page",
    )
```

> [!NOTE]
> `response_format` and `instructions` don't have to be both provided, you can use one or the other depending on your needs.


## Best Practices

1. **Define Clear Schemas**: When using structured data extraction, make sure your Pydantic models accurately represent the data you want to extract.

2. **Provide Clear Instructions**: The `instructions` parameter helps guide the extraction process. Be specific about what data you want to extract.

3. **Handle Optional Fields**: Use `| None` for fields that might not always be present in the source data.

4. **Error Handling**: Always check the `success` field in the structured response to ensure the extraction was successful.
