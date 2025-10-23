from notte_sdk import NotteClient, actions

client = NotteClient()

with client.Session(
    solve_captchas=True,
    browser_type="firefox",
) as session:
    session.execute(actions.Goto(url="https://www.google.com/recaptcha/api2/demo"))
    session.execute(actions.CaptchaSolve(captcha_type="recaptcha"))
