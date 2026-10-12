# @sniptest filename=solve_captchas.py
from notte_sdk import NotteClient

client = NotteClient()
with client.Session(solve_captchas=True, open_viewer=True) as session:
    # Navigate to a page with a CAPTCHA
    session.execute(type="goto", url="https://www.google.com/recaptcha/api2/demo")
    # Solve it with the built-in captcha solver
    session.execute(type="captcha_solve", captcha_type="recaptcha")
