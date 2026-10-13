from kernel import Kernel
from notte_sdk import NotteClient

client = NotteClient()
kernel = Kernel()

# Create browser on Kernel
kernel_browser = kernel.browsers.create()

# Connect Notte to Kernel's browser
with client.Session(cdp_url=kernel_browser.cdp_ws_url) as session:
    page = session.page
    page.goto("https://example.com")
