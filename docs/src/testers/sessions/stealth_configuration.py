# @sniptest filename=stealth_configuration.py
from notte_sdk import NotteClient
from notte_sdk.types import NotteProxy

client = NotteClient()

# Example stealth configuration
# this is just one possible configuration, with an obvious fingerprint
# rotating those values will raise your chances
with client.Session(
    solve_captchas=True,
    proxies=[NotteProxy.from_country("us")],
    browser_type="firefox",
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    viewport_width=1920,
    viewport_height=1080,
) as session:
    result = session.observe(url="https://example.com")
    print("Success with fallback configuration")
