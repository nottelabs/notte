import datetime as dt
from pathlib import Path
from typing import Annotated

from notte_sdk import NotteClient, RemoteSession, retry
from pydantic import BaseModel
from tqdm import tqdm

# ############################################
# CONFIG
# ############################################
RESULT_DIR = Path("nike_results")
# url = "https://gymbeam.pl/"
notte = NotteClient()
url = "https://www.nike.com/men"

# ############################################
# MODELS
# ############################################


class ProductCategory(BaseModel):
    name: Annotated[str, "The name of the product category"]
    url: Annotated[str, "The url of the product category"]
    menu: Annotated[str | None, "The menu of the product category (if it exists)"] = None


class ProductCategories(BaseModel):
    categories: list[ProductCategory]

    @staticmethod
    def example():
        return ProductCategories(
            categories=[
                ProductCategory(name="New Arrivals", menu="Featured", url="https://www.nike.com/w/new-3n82y"),
                ProductCategory(
                    name="Mother's day shop", menu="Featured", url="https://www.nike.com/w/mothers-day-ammh6"
                ),
                ProductCategory(
                    menu="Basketball", name="Shoes", url="https://www.nike.com/w/mens-basketball-shoes-nik1zy7ok"
                ),
            ]
        )


class ShoppingItem(BaseModel):
    name: Annotated[str, "The name of the product"]
    price: Annotated[float, "The price of the product"]
    url: Annotated[str, "The url of the product page "]
    image_src: Annotated[
        str | None, "The url or src path to the product image (i.e image.png or https://image.com/image.png)"
    ]


class ShoppingList(BaseModel):
    items: list[ShoppingItem]


# ############################################
# Agents
# ############################################


@retry(max_tries=5)
def scrape_categories(session: RemoteSession) -> ProductCategories:
    response = notte.Agent(session=session, max_steps=5).run(
        task=f"""
Get all the product categories from the nike.com home page (focus on the men's section).
Return the response in a json format ```{ProductCategories.model_json_schema()}```
Here is an example of successfull output

```json
{ProductCategories.example().model_dump_json()}
```

Your turn. Be as exhaustive as possible
""",
        url=url,
    )
    if response.answer is None:
        raise Exception("No response from the agent")
    categories = ProductCategories.model_validate_json(response.answer)
    return categories


@retry(max_tries=3)
def scrape_products(session: RemoteSession, cat: ProductCategory) -> ShoppingList:
    data = session.scrape(
        url=cat.url,
        response_format=ShoppingList,
        instructions=f"Get all the items from the {cat.name} category. Make sure to fill the image_src field with the correct image url",
        only_main_content=True,
        scrape_images=True,
        scrape_links=True,
        use_llm=False,
        # /!\ Experimental feature to reduce the number of tokens and speed up the scraping process
        use_link_placeholders=True,
    )
    if data.structured is None:
        raise ValueError("No structured response from the agent")
    items: ShoppingList = data.structured.get()  # type: ignore
    return items


# ############################################
# Main
# ############################################


def scrape_nike_products():
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = RESULT_DIR / timestamp
    run_dir.mkdir(exist_ok=True, parents=True)

    with notte.Session(headless=False) as session:
        categories = scrape_categories(session)
        _ = (run_dir / "categories.json").write_text(categories.model_dump_json())
        outputs: list[list[ShoppingItem]] = []
        for category in tqdm(categories.categories):
            try:
                items = scrape_products(session, category)
                _ = (run_dir / f"category_{category.name}.json").write_text(items.model_dump_json())
                outputs.append(items.items)
            except Exception as e:
                print(f"Error scraping {category.name}: {e}")
                outputs.append([])
        print(f"""
Scraping results:

* Total categories scraped: {len(categories.categories)}.
* Total items scraped: {sum([len(output) for output in outputs])}.

Scraping data saved in {run_dir}
""")
        session.replay().save(str(run_dir / "replay.webp"))


if __name__ == "__main__":
    scrape_nike_products()
