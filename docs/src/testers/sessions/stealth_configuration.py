# @sniptest filename=stealth_configuration.py
# @sniptest show=1-17
from notte_sdk import NotteClient

client = NotteClient()

# Example stealth configuration
# this is just one possible configuration, with an obvious fingerprint
# rotating those values will raise your chances
with client.Session(
    solve_captchas=True,
    proxies="us",
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    viewport_width=1920,
    viewport_height=1080,
) as session:
    session.execute(type="goto", url="https://example.com")
    result = session.observe()
    print("Success with fallback configuration")

status = session.status()
assert status.proxies is True
assert (
    status.user_agent
    == "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
assert status.viewport_width == 1920
assert status.viewport_height == 1080
