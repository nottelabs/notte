import asyncio
import os
import subprocess

from bridge import cdp_bridge
from notte_sdk import NotteClient
from selenium import webdriver
from selenium.webdriver.chrome.service import Service


def connect_driver(address: str):
    options = webdriver.ChromeOptions()
    options.debugger_address = address
    return webdriver.Chrome(
        service=Service(executable_path=os.environ["CHROMEDRIVER_PATH"], log_output=subprocess.DEVNULL),
        options=options,
    )


def read_page(address: str):
    driver = connect_driver(address)
    try:
        driver.set_page_load_timeout(30)
        driver.get("https://example.com")
        return driver.title
    finally:
        driver.quit()


async def main():
    with NotteClient().Session(max_duration_minutes=3, proxies=False, browser_type="chrome") as session:
        async with cdp_bridge(session.cdp_url()) as address:
            return await asyncio.to_thread(read_page, address)


if __name__ == "__main__":
    print(asyncio.run(main()))
