import os

from dotenv import load_dotenv
from notte_sdk import NotteClient

# Load environment variables
_ = load_dotenv(".env.example")

landing_examples = [
    # task str, URL str | None, use vault bool
    ["Find the latest job openings on notte.cc", None, False],
    [
        "Sign in with google, enter the zip code 94103, and skip through menus to view my current meal selection",
        "https://www.cookunity.com/",
        True,
    ],
    # TODO: this uses Google auth but the actual landing page uses email sign-in
    ["Visit github.com/trending and return the top 3 repositories shown.", None, False],
    ["Check if there are any new blog posts on notte.cc/blog", None, False],
    ["Go to bbc.com and click on the first headline in the 'Sport' section. Return its title.", None, False],
    ["Go to weather.com and tell me the current temperature in New York City.", None, False],
]


# run landing page examples
def main():
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))

    for task, url, vault in landing_examples[3:]:
        with client.Session() as session:
            if vault:
                vault = client.Vault()
                email = os.getenv("NOTTE_VAULT_TEST_EMAIL")
                assert email is not None
                pwd = os.getenv("NOTTE_VAULT_TEST_PASSWORD")
                assert pwd is not None
                _ = vault.add_credentials(
                    url="https://google.com",
                    email=email,
                    password=pwd,
                )
            else:
                vault = None

            agent_kwargs = {
                "session": session,
                "reasoning_model": "vertex_ai/gemini-2.0-flash",
                "max_steps": 15,
                **({"vault": vault} if vault is not None else {}),
            }
            agent = client.Agent(**agent_kwargs)
            run_kwargs = {"task": task, **({"url": url} if url is not None else {})}
            response = agent.run(**run_kwargs)

            if not response.success:
                exit(-1)


if __name__ == "__main__":
    main()
