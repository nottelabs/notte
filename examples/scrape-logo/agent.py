from notte_core.data.space import DataSpace
from notte_sdk import NotteClient
from pydantic import BaseModel

notte: NotteClient = NotteClient()


class Logo(BaseModel):
    logo: str


def scrape_logo(url: str) -> DataSpace:
    with notte.Session(headless=False) as session:
        return session.scrape(
            url=url,
            instructions=f"Get the logo of the website {url}",
            only_main_content=False,
            scrape_images=True,
            scrape_links=True,
            response_format=Logo,
        )


def extract_logo(data: DataSpace, url: str) -> str | None:
    # Case 1: structured output worked
    if data.structured is not None and data.structured.success:
        logo: Logo = data.structured.get()  # type: ignore
        logo_url = logo.logo
        if not logo_url.startswith("http"):
            if logo_url.startswith("/"):
                logo_url = logo_url[1:]
            if url.endswith("/"):
                logo_url = f"{url}{logo_url}"
            else:
                logo_url = f"{url}/{logo_url}"
        return logo_url
    # Case 2: there is a logo image in data.images
    if data.images is None:
        return None
    for image in data.images:
        if image.description is not None and "logo" in image.description.lower():
            return image.url
    # Case 3: fallback to favicon
    return data.images[0].url


if __name__ == "__main__":
    url = "https://gymbeam.pl"
    data = scrape_logo(url)
    logo_url = extract_logo(data, url)
    if logo_url is not None:
        print(f"Logo URL: {logo_url}")
    else:
        print("No logo found")
        exit(-1)
