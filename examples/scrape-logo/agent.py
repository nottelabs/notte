from loguru import logger
from notte_sdk import NotteClient
from pydantic import BaseModel

notte: NotteClient = NotteClient()


class Logo(BaseModel):
    logo: str

    def get_url(self, url: str) -> str:
        logo_url = self.logo
        if not logo_url.startswith("http"):
            if logo_url.startswith("/"):
                logo_url = logo_url[1:]
            if url.endswith("/"):
                logo_url = f"{url}{logo_url}"
            else:
                logo_url = f"{url}/{logo_url}"
        return logo_url


def scrape_logo_url(url: str) -> str | None:
    with notte.Session() as session:
        _ = session.execute({"type": "goto", "url": url})
        data = session.scrape(
            instructions=f"Get the logo of the website {url}",
            response_format=Logo,
            only_main_content=False,
            scrape_images=True,
            scrape_links=True,
        )
        if data.success:
            # Case 1: structured output worked
            logger.info(f"Logo found for {url}: {data.get().get_url(url)}")
            return data.get().get_url(url)
        images = session.scrape(only_images=True)
        for image in images:
            # Case 2: there is a logo image in data.images
            if image.description is not None and "logo" in image.description.lower():
                logger.info(f"Logo found for {url}: {image.url}")
                return image.url
        # Case 3: fallback to favicon
        if len(images) > 0:
            return images[0].url
    logger.error(f"No logo found for {url}")
    return None


def run(url: str):
    return scrape_logo_url(url)


if __name__ == "__main__":
    _ = run(url="https://gymbeam.pl")
