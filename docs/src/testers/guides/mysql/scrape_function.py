# @sniptest filename=scrape_function.py
from urllib.parse import urlsplit

import requests
from pydantic import BaseModel, Field
from pydantic.v1 import BaseSettings

NOTTE_REQUIRED_SECRETS = ["MYSQL_INGEST_URL", "MYSQL_INGEST_TOKEN"]


class ScrapeSettings(BaseSettings):
    notte_api_key: str
    notte_api_url: str = "https://api.notte.cc"


class IngestSettings(BaseSettings):
    mysql_ingest_url: str
    mysql_ingest_token: str


class PageData(BaseModel):
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)


def scrape_page(url: str) -> PageData:
    settings = ScrapeSettings()
    response = requests.post(
        settings.notte_api_url.rstrip("/") + "/scrape",
        headers={"Authorization": f"Bearer {settings.notte_api_key}"},
        json={
            "url": url,
            "instructions": "Extract the page title and a short description of the page.",
            "response_format": PageData.model_json_schema(),
            "only_main_content": True,
        },
        timeout=120,
    )
    response.raise_for_status()
    structured = response.json().get("structured") or {}
    if not structured.get("success"):
        raise RuntimeError("The scrape did not produce structured data")
    return PageData.model_validate(structured["data"])


def run(url: str) -> dict:
    settings = IngestSettings()
    receiver = settings.mysql_ingest_url
    if urlsplit(receiver).scheme != "https":
        raise ValueError("MYSQL_INGEST_URL must use HTTPS")
    page = scrape_page(url)
    response = requests.post(
        receiver,
        headers={"Authorization": f"Bearer {settings.mysql_ingest_token}"},
        json={"url": url, "data": page.model_dump()},
        timeout=30,
        allow_redirects=False,
    )
    response.raise_for_status()
    if response.status_code != 200 or response.json().get("saved") is not True:
        raise RuntimeError("The receiver did not confirm the database write")
    return {"url": url, "saved": True}
