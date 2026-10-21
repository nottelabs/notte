# @sniptest filename=mysql_receiver.py
import os
import secrets

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from scrape_function import PageData
from scrape_to_mysql import save_page

app = FastAPI()


class ScrapeResult(BaseModel):
    url: str = Field(min_length=1, max_length=512, pattern=r"^https?://")
    data: PageData


@app.post("/ingest")
def ingest(payload: ScrapeResult, authorization: str = Header(default="")) -> dict:
    expected = f"Bearer {os.environ['MYSQL_INGEST_TOKEN']}"
    if not secrets.compare_digest(authorization.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid ingest token")
    save_page(str(payload.url), payload.data)
    return {"saved": True}
