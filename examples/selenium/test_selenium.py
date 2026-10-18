import asyncio
import os
import time
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import main as demo
import requests
from bridge import cdp_bridge
from notte_sdk import NotteClient
from selenium.common.exceptions import InvalidSelectorException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


@unittest.skipUnless(os.environ.get("NOTTE_SELENIUM_LIVE") == "1", "Live browser tests are opt-in")
class SeleniumLiveTests(unittest.TestCase):
    @contextmanager
    def owned(self):
        self.assertTrue(os.environ.get("NOTTE_API_URL"), "Choose the test API explicitly")
        client = NotteClient()
        start = client.sessions.start
        ids = []

        def track(*args, **kwargs):
            response = start(*args, **kwargs)
            ids.append(response.session_id)
            return response

        with (
            patch.object(client.sessions, "start", side_effect=track),
            patch.object(demo, "NotteClient", return_value=client),
        ):
            try:
                yield client
            finally:
                self.assertEqual(len(ids), 1, "Expected exactly one owned browser")
                for attempt in range(30):
                    status = client.sessions.status(session_id=ids[0])
                    if status.status == "closed":
                        break
                    time.sleep(0.5)
                self.assertEqual(status.status, "closed", "Owned browser did not close")

    def test_original_demo(self):
        with self.owned():
            self.assertEqual(asyncio.run(demo.main()), "Example Domain")

    def test_standard_actions_and_reconnect(self):
        with self.owned() as client:
            with client.Session(
                max_duration_minutes=3, proxies=False, browser_type="chrome", viewport_width=1024, viewport_height=768
            ) as session:

                async def run():
                    async with cdp_bridge(session.cdp_url()) as address:

                        def commands():
                            driver = demo.connect_driver(address)
                            try:
                                driver.set_page_load_timeout(30)
                                driver.get("https://example.com")
                                self.assertEqual(driver.title, "Example Domain")
                                driver.execute_script(
                                    "document.body.innerHTML='<input id=name><button id=submit>Send</button>'; document.querySelector('#submit').onclick=event=>event.target.textContent='Sent'"
                                )
                                field = WebDriverWait(driver, 10).until(
                                    EC.visibility_of_element_located((By.ID, "name"))
                                )
                                field.send_keys("Notte")
                                ActionChains(driver).move_to_element(
                                    driver.find_element(By.ID, "submit")
                                ).click().perform()
                                self.assertEqual(driver.find_element(By.ID, "submit").text, "Sent")
                            finally:
                                driver.quit()
                            driver = demo.connect_driver(address)
                            try:
                                self.assertEqual(driver.find_element(By.ID, "name").get_attribute("value"), "Notte")
                            finally:
                                driver.quit()
                            metadata = requests.get(f"http://{address}/json/version", timeout=5).json()
                            self.assertTrue(metadata["webSocketDebuggerUrl"].startswith(f"ws://{address}/"))
                            self.assertFalse(
                                session.cdp_url() in str(metadata), "Discovery must hide the authenticated endpoint"
                            )
                            self.assertEqual(
                                requests.get(
                                    f"http://{address}/json/version",
                                    headers={"Origin": "https://example.com"},
                                    timeout=5,
                                ).status_code,
                                403,
                            )

                        await asyncio.to_thread(commands)
                    with self.assertRaises(requests.ConnectionError):
                        await asyncio.to_thread(requests.get, f"http://{address}/json/version", timeout=1)

                asyncio.run(run())

    def test_real_command_failure_closes_browser(self):
        with self.owned() as client:
            with self.assertRaises(InvalidSelectorException):
                with client.Session(max_duration_minutes=3, proxies=False, browser_type="chrome") as session:

                    async def run():
                        async with cdp_bridge(session.cdp_url()) as address:

                            def fail():
                                driver = demo.connect_driver(address)
                                try:
                                    driver.find_element(By.CSS_SELECTOR, "[")
                                finally:
                                    driver.quit()

                            await asyncio.to_thread(fail)

                    asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
