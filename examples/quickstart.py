import os
import sys

from notte_sdk import NotteClient

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python quickstart.py '<your task>' <max_steps> <reasoning_model>")
        sys.exit(1)
    task = sys.argv[1]
    try:
        max_steps = int(sys.argv[2])
    except ValueError:
        print("max_steps must be an integer")
        sys.exit(1)
    reasoning_model = sys.argv[3]

    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))

    with client.Session(headless=False) as session:
        agent = client.Agent(reasoning_model=reasoning_model, max_steps=max_steps, session=session)
        response = agent.run(task=task)
