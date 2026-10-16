from kernel import Kernel
from notte_sdk import NotteClient

# Initialize clients
client = NotteClient()
kernel = Kernel()

# Create browser on Kernel
kernel_browser = kernel.browsers.create()

try:
    # Connect Notte to Kernel's browser
    with client.Session(cdp_url=kernel_browser.cdp_ws_url) as session:
        # Use Notte's features
        page = session.page
        page.goto("https://example.com")

        # Extract data with Notte's scraping
        result = session.scrape(instructions="Find the contact email")

        print(f"Result: {result}")

finally:
    # Clean up Kernel browser
    kernel.browsers.delete_by_id(kernel_browser.session_id)
