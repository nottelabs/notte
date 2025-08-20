import getpass
import json
from pathlib import Path

from loguru import logger
from notte_core.actions import FormFillAction

from notte_sdk.endpoints.sessions import RemoteSession


def generate_cookies(session: RemoteSession, url: str, output_path: str) -> None:
    if not output_path.endswith(".json"):
        raise ValueError(f"Output path must end with .json: {output_path}")

    _ = session.execute(dict(type="goto", url=url))

    email = input("Enter your email: ")
    password = getpass.getpass(prompt="Enter your password: ")

    form_fill_action = FormFillAction(value=dict(email=email, current_password=password))  # type: ignore

    res = session.execute(form_fill_action)
    if not res.success:
        logger.error(f"Failed to fill email & password: {res.message}")
        raise ValueError("Failed to fill email & password")
    logger.info("✅ Successfully filled email & password")

    obs = session.observe(instructions="Click on the 'Sign in' button", perception_type="deep")
    signin = obs.space.first()
    res = session.execute(signin)
    if not res.success:
        logger.error(f"Failed to click on the 'Sign in' button: {res.message}")
        return
    logger.info("✅ Successfully clicked on the 'Sign in' button")

    logger.info("Waiting for 5 seconds to let the page load...")
    _ = session.execute(dict(type="wait", time_ms=5000))
    # save cookies
    cookies = session.get_cookies()

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(cookies, f)

    if len(cookies) == 0:
        logger.error("❌ No cookies created during the login process. Try again or do it manually.")

    logger.info(f"🔥 Successfully saved {len(cookies)} cookies to {output_path}")
