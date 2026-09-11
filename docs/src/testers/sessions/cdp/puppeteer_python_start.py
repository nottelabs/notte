import subprocess

from notte_sdk import NotteClient

client = NotteClient()

with client.Session(timeout_minutes=10) as session:
    cdp_url = session.cdp_url()

    # Pass CDP URL to Node.js script
    result = subprocess.run(["node", "puppeteer_script.js", cdp_url], capture_output=True, text=True)

    print(result.stdout)
