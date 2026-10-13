# @sniptest filename=recaptcha_solve_action.py
# @sniptest typecheck_only=true
from notte_sdk import NotteClient

DEMO_URL = "https://nopecha.com/captcha/recaptcha#easy"
client = NotteClient()

with client.Session(solve_captchas=True, proxies=True, open_viewer=True) as session:
    session.execute(type="goto", url=DEMO_URL)

    result = session.execute(
        type="captcha_solve",
        captcha_type="recaptcha",
        raise_on_failure=False,
    )

    if not result.success:
        raise RuntimeError(f"reCAPTCHA solve failed: {result.message}")

    session.execute(type="wait", time_ms=2000)
