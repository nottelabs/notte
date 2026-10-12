import os
import sys

from notte_sdk import NotteClient

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python quickstart.py <url>")
        sys.exit(1)
    url = sys.argv[1]

    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))

    with client.Session(open_viewer=True) as session:
        _ = session.execute(type="goto", url=url)
        print(session.scrape())
