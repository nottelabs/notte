# Web Scraping with Notte

Notte provides powerful tools for web scraping that can extract both raw content and structured data from web pages. This tutorial will guide you through the different ways you can use Notte for web scraping.

## Basic Web Scraping

The simplest way to scrape a webpage is to extract its content as markdown. This is useful when you want to preserve the page's structure and formatting.

### Using the Notte Browser Environment

```python
from notte_browser.session import NotteSession

async with NotteSession() as page:
    data = await page.scrape(url="https://www.notte.cc")
    print(data.markdown)
```

### Using the Notte SDK

If you're working with the Notte SDK, you can achieve the same result:

```python
import os
from notte_sdk import NotteClient

client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
with client.Session() as page:
    data = page.scrape(url="https://www.notte.cc")
    print(data.markdown)
```

## Structured Data Extraction

For more sophisticated use cases, you can extract structured data from web pages by defining a schema using Pydantic models. This is particularly useful when you need to extract specific information like product details, pricing plans, or article metadata.

### Example: Extracting Pricing Plans

Let's say you want to extract pricing information from a website. First, define your data models:

```python
from pydantic import BaseModel

class PricingPlan(BaseModel):
    name: str
    price_per_month: int | None
    features: list[str]

class PricingPlans(BaseModel):
    plans: list[PricingPlan]
```

Then use these models to extract structured data:

```python
from notte_browser.session import NotteSession

async with NotteSession() as page:
    data = await page.scrape(
        url="https://www.notte.cc",
        response_format=PricingPlans,
        instructions="Extract the pricing plans from the page",
    )
    print(data.structured.get()) # will raise an error in case of scraping failure
```

### Using the SDK for Structured Data

The same structured extraction can be done using the SDK:

```python
import os
from notte_sdk import NotteClient

client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
with client.Session() as page:
    data = page.scrape(
        url="https://www.notte.cc",
        response_format=PricingPlans,
        instructions="Extract the pricing plans from the page",
    )
```

## Best Practices

1. **Define Clear Schemas**: When using structured data extraction, make sure your Pydantic models accurately represent the data you want to extract.

2. **Provide Clear Instructions**: The `instructions` parameter helps guide the extraction process. Be specific about what data you want to extract.

3. **Handle Optional Fields**: Use `| None` for fields that might not always be present in the source data.

4. **Error Handling**: Always check the `success` field in the structured response to ensure the extraction was successful.

## Advanced Usage

You can combine both approaches - extract the raw markdown and structured data in a single request:

```python
async with NotteSession() as page:
    data = await page.scrape(
        url="https://www.notte.cc",
        response_format=PricingPlans,
        instructions="Extract the pricing plans from the page",
    )

    # Access both raw and structured data
    print("Raw content:", data.markdown)
    print("Structured data:", data.structured.get())
```

This gives you the flexibility to work with both the raw content and structured data as needed for your application.
