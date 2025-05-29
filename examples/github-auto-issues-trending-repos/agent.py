import json
import os
from pathlib import Path
from typing import Annotated, Any

import pandas as pd
from dotenv import load_dotenv
from halo import Halo  # type: ignore
from loguru import logger
from notte_sdk import NotteClient, retry
from notte_sdk.endpoints.vaults import NotteVault
from pydantic import BaseModel

_ = load_dotenv()

client = NotteClient()

# TODO: update the prompt based on your needs
ISSUE_TASK_PROMPT = r"""
Look for github issues on the repo {repo_url} with the following details:
- Title: "{repo}: a great repo"
- Body: "This has to be the best issue I have ever posted in my life"

If the issue doesn't exist, create it. If it does exist, your job is done.
CRITICAL: Your output has to be a valid JSON object with the following structure:

{{
    "url": "url_of_the_issue",
    "existed": bool
}}
"""

# ###############################################################################
# ################################ TYPES ########################################
# ###############################################################################


class TrendingRepo(BaseModel):
    org: Annotated[str, "The organization name of the repository. E.g. 'example_org'"]
    repo: Annotated[str, "The repository name. E.g. 'example_repo'"]
    url: Annotated[str, "The URL of the repository. E.g. 'https://github.com/example_org/example_repo'"]
    desc: Annotated[str, "The description of the repository. E.g. 'This is an example repository'"]
    n_stars: Annotated[int | None, "The number of stars of the repository. E.g. 100"]
    n_forks: Annotated[int | None, "The number of forks of the repository. E.g. 100"]


class TrendingRepos(BaseModel):
    trending: list[TrendingRepo]


class RepoIssue(BaseModel):
    issue_url: str
    created_issue: bool


class TrendingRepoWithIssue(TrendingRepo, RepoIssue):
    pass


class CsvLogger:
    csv_path: Path = Path("trending.csv")
    trending: pd.DataFrame

    def __init__(self):
        if not self.csv_path.exists():
            df = pd.DataFrame(
                [],
                columns=list(TrendingRepoWithIssue.model_fields.keys()),
            )
            df.to_csv(self.csv_path, index=False)

        self.trending = pd.read_csv(self.csv_path)  # type: ignore

    def log(self, data: list[TrendingRepoWithIssue]):
        to_add: list[dict[str, Any]] = []

        for issue in data:
            if self.check_if_issue_exists(issue):
                logger.info(f"Issue already exists at: {issue.issue_url}. Skipping...")
                continue

            to_add.append(issue.model_dump())

        self.trending = pd.concat((self.trending, pd.DataFrame(to_add)))
        self.trending.to_csv(self.csv_path, index=False)

    def check_if_issue_exists(self, repo: TrendingRepo) -> bool:
        return any(repo.url == self.trending.url)  # type: ignore


def get_or_create_vault() -> NotteVault:
    vault_id = os.getenv("NOTTE_VAULT_ID")
    if vault_id is not None and len(vault_id) > 0:
        return client.vaults.get(vault_id)
    # create a new vault and save it the `.env` file
    with Halo(text="Creating a new vault ", spinner="dots"):
        vault = client.vaults.create()
        vault_id = vault.vault_id
        try:
            # get vault
            logger.info(f"Loading vault with id: {vault_id}...")

            logger.info("Added github credentials to vault...")
            _ = vault.add_credentials(
                url="https://github.com",
                email=os.environ["AUTO_ISSUES_GITHUB_EMAIL"],
                password=os.environ["AUTO_ISSUES_GITHUB_PASSWORD"],
                mfa_secret=os.environ["AUTO_ISSUES_GITHUB_MFA_SECRET"],
            )
            # store vault id in .env file only if created successfully
            logger.info(f"Vault created with id: {vault_id}. Storing it in .env file...")
            with open(".env", "a") as f:
                _ = f.write(f"NOTTE_VAULT_ID={vault_id}\n")
        except Exception:
            _ = client.vaults.delete_vault(vault_id)
            raise

        return vault


# ###############################################################################
# ################################ AGENTS #######################################
# ###############################################################################


@retry(max_tries=3, delay_seconds=5, error_message="Failed to fetch trending repos. Try again later...")
def fetch_trending_repos() -> list[TrendingRepo]:
    data = client.scrape(
        url="https://github.com/trending",
        response_format=TrendingRepos,
        instructions="Retrieve the top 3 trending repositories",
        use_llm=True,
    )
    trending_repos: TrendingRepos = data.structured.get()  # type: ignore
    return trending_repos.trending


@retry(max_tries=3, delay_seconds=5, error_message="Failed to create issue. Try again later...")
def create_github_issue(repo: TrendingRepo, vault: NotteVault) -> RepoIssue | None:
    with client.Session(
        headless=False,
        proxies=True,
        timeout_minutes=3,
        chrome_args=[],
    ) as session:
        agent = client.Agent(session=session, vault=vault)
        response = agent.run(
            task=ISSUE_TASK_PROMPT.format(repo_url=repo.url, repo=repo.repo),
            url="https://github.com",
        )
    if not response.success:
        error_msg = f"Agent {agent.agent_id} failed to create issue for {repo.url}: {response.answer}"
        logger.error(error_msg)
        raise Exception(error_msg)

    if response.answer:
        issue_data = json.loads(response.answer)
        issue_url = issue_data.get("url")
        if issue_data and issue_data.get("existed"):
            print(f"Issue already exists at: {issue_data.get('url')}")
            return RepoIssue(issue_url=issue_url, created_issue=False)
        elif issue_data:
            print(f"Successfully created issue: {issue_data.get('url')}")
            return RepoIssue(issue_url=issue_url, created_issue=True)
    return None


def create_new_issues():
    csv_logger = CsvLogger()
    issues_to_add: list[TrendingRepoWithIssue] = []
    vault = get_or_create_vault()

    with Halo(text="Fetching the trending repos ", spinner="dots"):
        trending_repos = fetch_trending_repos()

    for repo in trending_repos:
        if csv_logger.check_if_issue_exists(repo):
            continue
        with Halo(text=f"Creating issue for {repo.repo} ", spinner="dots"):
            issue = create_github_issue(repo, vault)

        if issue is not None:
            issues_to_add.append(TrendingRepoWithIssue(**repo.model_dump(), **issue.model_dump()))

    csv_logger.log(issues_to_add)


# ###############################################################################
# ################################## MAIN #######################################
# ###############################################################################

if __name__ == "__main__":
    create_new_issues()
