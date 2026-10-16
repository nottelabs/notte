# /// script
# requires-python = ">=3.11"
# dependencies = ["google-auth[requests]>=2.60.0"]
# ///
"""Configure CI's optional direct Vertex matrix route using OAuth credentials, outside notte-llm.

Run with `uv run --script .github/scripts/configure_llm.py`. The auth action
creates the credential file. Refreshing those credentials uses the OAuth token
endpoint directly, without requiring the IAM Service Account Credentials API.
"""

import os
from pathlib import Path

import google.auth
from google.auth.transport.requests import Request


def main() -> None:
    env_file = Path(os.environ["GITHUB_ENV"])
    credentials, project = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(Request())
    if not project or not credentials.token:
        raise RuntimeError("Vertex CI requires a project and an OAuth access token")
    # Register the newly minted token before a later step can display its environment.
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::add-mask::{credentials.token}", flush=True)
    with env_file.open("a") as output:
        _ = output.write(
            f"NOTTE_VERTEX_BASE_URL=https://aiplatform.googleapis.com/v1/projects/{project}"
            "/locations/global/endpoints/openapi\n"
            f"NOTTE_VERTEX_API_KEY={credentials.token}\n"
            "NOTTE_VERTEX_MODEL=google/gemini-3.5-flash-lite\n"
        )


if __name__ == "__main__":
    main()
