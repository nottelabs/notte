import os
import sys

from notte_sdk import NotteClient

if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else "Search for AI news"
    max_steps = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    reasoning_model = sys.argv[3] if len(sys.argv) > 3 else "openai/gpt-4o"

    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))

    with client.Session() as session:
        agent = client.Agent(reasoning_model=reasoning_model, max_steps=max_steps, session=session)
        response = agent.run(task=task)
