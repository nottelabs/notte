"""Test a web app running in a Daytona sandbox with a Notte cloud browser.

The app is served from inside the sandbox and exposed on a signed preview URL. A
Notte browser then opens that URL twice: once from this script with Playwright
over CDP, and once from inside the sandbox with the Notte CLI, the way an agent
running in the sandbox would.
"""

import json
import os
import shlex
from pathlib import Path

from daytona import Daytona, Sandbox, SessionExecuteRequest
from dotenv import load_dotenv
from notte_sdk import NotteClient

PORT = 3000
APP_DIR = "/home/daytona/app"
OUTPUT_DIR = Path(__file__).parent / "output"
# Preview URLs show a warning page to browsers on first load; this header skips it.
PREVIEW_HEADERS = {"X-Daytona-Skip-Preview-Warning": "true"}

# A small to-do app, standing in for whatever your agent builds in the sandbox.
APP_HTML = """<!doctype html>
<html>
  <head><meta charset="utf-8"><title>Sandbox To-dos</title></head>
  <body style="font-family: sans-serif; max-width: 480px; margin: 40px auto">
    <h1>Sandbox To-dos</h1>
    <form id="add">
      <input id="title" name="title" placeholder="New to-do" aria-label="New to-do">
      <button type="submit">Add</button>
    </form>
    <ul id="todos">
      <li>Write the app</li>
      <li>Start the server</li>
    </ul>
    <p id="count">2 to-dos</p>
    <script>
      document.getElementById("add").addEventListener("submit", (event) => {
        event.preventDefault();
        const input = document.getElementById("title");
        if (!input.value.trim()) return;
        const item = document.createElement("li");
        item.textContent = input.value.trim();
        document.getElementById("todos").appendChild(item);
        const count = document.querySelectorAll("#todos li").length;
        document.getElementById("count").textContent = `${count} to-dos`;
        input.value = "";
      });
    </script>
  </body>
</html>
"""


class CommandError(RuntimeError):
    """A command in the sandbox exited with a non-zero code."""


def run(sandbox: Sandbox, command: str, env: dict[str, str] | None = None, timeout: int = 120) -> str:
    """Run a command in the sandbox and return its output, raising if it fails."""
    result = sandbox.process.exec(command, env=env, timeout=timeout)
    if result.exit_code != 0:
        raise CommandError(f"`{command}` exited with {result.exit_code}: {result.result.strip()}")
    return result.result


def start_app(sandbox: Sandbox) -> str:
    """Serve the app from the sandbox and return a signed preview URL for it."""
    sandbox.fs.upload_file(APP_HTML.encode(), f"{APP_DIR}/index.html")
    sandbox.process.create_session("app")
    sandbox.process.execute_session_command(
        "app",
        SessionExecuteRequest(command=f"cd {APP_DIR} && python3 -m http.server {PORT}", run_async=True),
    )
    # Wait until the server accepts connections before handing the URL to the browser.
    run(
        sandbox,
        f"bash -c 'for i in $(seq 1 50); do curl -sf http://localhost:{PORT} > /dev/null && exit 0; sleep 0.2; done; exit 1'",
    )
    # A signed URL carries its token, so the browser needs no auth header.
    return sandbox.create_signed_preview_url(PORT, expires_in_seconds=3600).url


def check_with_playwright(notte: NotteClient, url: str) -> list[str]:
    """Open the app in a Notte browser from this script and return its to-dos."""
    with notte.Session(extra_http_headers=PREVIEW_HEADERS) as session:
        print(f"Watch the browser live: {session.response.viewer_url}")

        # session.page is a Playwright page connected to the Notte browser over CDP.
        page = session.page
        page.goto(url)
        todos = page.locator("#todos li").all_inner_texts()
        print(f"Playwright saw '{page.title()}' with to-dos: {todos}")
        OUTPUT_DIR.mkdir(exist_ok=True)
        page.screenshot(path=OUTPUT_DIR / "app.png")
        print(f"Screenshot saved to {OUTPUT_DIR / 'app.png'}")
        return todos


def install_notte(sandbox: Sandbox) -> None:
    """Install the latest Notte CLI release and the Notte skill for coding agents."""
    run(sandbox, "bash -c 'curl -fsSL https://notte.cc/install-cli.sh | sh'")
    # Installs into ~/.agents/skills, where Claude Code, Codex and other agents pick it up.
    run(sandbox, "bash -c 'cd /home/daytona && notte skill add --yes'", timeout=240)
    skills = run(sandbox, "ls /home/daytona/.agents/skills").split()
    print(f"Installed the Notte CLI and skills: {', '.join(skills)}")


def check_with_notte_cli(sandbox: Sandbox, url: str) -> str:
    """Drive a Notte browser from inside the sandbox with CLI commands and return the scraped page."""
    env = {"NOTTE_API_KEY": os.environ["NOTTE_API_KEY"]}
    if api_url := os.environ.get("NOTTE_API_URL"):
        env["NOTTE_API_URL"] = api_url
    headers = shlex.quote(json.dumps(PREVIEW_HEADERS))
    started = run(sandbox, f"notte sessions start --extra-http-headers {headers} -o json", env=env)

    # From here on the session exists, so always try to stop it.
    try:
        session = json.loads(started)
        # viewer_url is optional in the session response.
        print(f"Notte CLI started session {session['session_id']}, watch it live: {session.get('viewer_url')}")
        commands = [
            f"notte page goto {shlex.quote(url)}",
            "notte page fill '#title' 'Ship the Daytona example'",
            "notte page click 'button[type=submit]'",
            "notte page scrape --only-main-content",
        ]
        output = ""
        for command in commands:
            print(f"$ {command}")
            output = run(sandbox, command, env=env).strip()
            print(output)
        return output
    finally:
        # Stop the session even when a command fails. Warn instead of raising, so a
        # failed stop never hides the original error.
        try:
            run(sandbox, "notte sessions stop --yes", env=env)
            print("Notte CLI session stopped")
        except CommandError as error:
            print(f"Warning: could not stop the Notte CLI session: {error}")


def main() -> None:
    load_dotenv()
    notte = NotteClient()
    daytona = Daytona()
    sandbox = daytona.create()
    print(f"Created sandbox {sandbox.id}")

    try:
        url = start_app(sandbox)
        print(f"App is live on port {PORT} at a signed preview URL")
        check_with_playwright(notte, url)
        install_notte(sandbox)
        check_with_notte_cli(sandbox, url)
    finally:
        # Warn instead of raising, so a failed delete never hides the original error.
        try:
            daytona.delete(sandbox)
            print("Sandbox deleted")
        except Exception as error:
            print(f"Warning: could not delete sandbox {sandbox.id}: {error}")


if __name__ == "__main__":
    main()
