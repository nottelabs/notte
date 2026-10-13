import json
from pathlib import Path

import pytest
from notte_browser.session import NotteSession
from notte_core.common.config import CookieDict
from notte_core.utils.files import create_or_append_cookies_to_file


def cookie(name: str, value: str) -> CookieDict:
    return {"name": name, "value": value, "domain": "example.com", "path": "/", "httpOnly": False}


def test_saving_cookies_merges_one_entry_per_cookie(tmp_path: Path) -> None:
    cookie_file = tmp_path / "cookies.json"

    create_or_append_cookies_to_file(cookie_file, [cookie("a", "1"), cookie("b", "1")])
    create_or_append_cookies_to_file(cookie_file, [cookie("a", "2"), cookie("b", "1")])

    assert json.loads(cookie_file.read_text()) == [cookie("a", "2"), cookie("b", "1")]


def test_saving_keeps_cookies_another_session_saved(tmp_path: Path) -> None:
    cookie_file = tmp_path / "cookies.json"

    create_or_append_cookies_to_file(cookie_file, [cookie("a", "1")])
    create_or_append_cookies_to_file(cookie_file, [cookie("b", "1")])

    assert json.loads(cookie_file.read_text()) == [cookie("a", "1"), cookie("b", "1")]


@pytest.mark.asyncio
async def test_each_session_stop_saves_the_cookies_once(tmp_path: Path) -> None:
    cookie_file = tmp_path / "cookies.json"
    for _ in range(3):
        async with NotteSession(headless=True, cookie_file=cookie_file) as session:
            await session.aset_cookies(
                cookies=[
                    {
                        "name": "sid",
                        "value": "v",
                        "domain": "example.com",
                        "path": "/",
                        "httpOnly": False,
                        "expires": -1,
                    }
                ]
            )

    saved = json.loads(cookie_file.read_text())
    assert [c["name"] for c in saved] == ["sid"]


@pytest.mark.asyncio
async def test_cookies_differing_only_by_partition_are_both_saved(tmp_path: Path) -> None:
    cookie_file = tmp_path / "cookies.json"
    partitioned: list[CookieDict] = [
        {
            "name": "chips",
            "value": site,
            "domain": "widget.example.com",
            "path": "/",
            "httpOnly": False,
            "secure": True,
            "sameSite": "None",
            "partitionKey": f"https://{site}.example",
        }
        for site in ("first", "second")
    ]
    async with NotteSession(headless=True, cookie_file=cookie_file) as session:
        await session.aset_cookies(cookies=partitioned)

    saved = json.loads(cookie_file.read_text())
    assert sorted((c["value"], c["partitionKey"]) for c in saved if c["name"] == "chips") == [
        ("first", "https://first.example"),
        ("second", "https://second.example"),
    ]
