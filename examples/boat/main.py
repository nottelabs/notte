"""Test a web app running in a boat sandbox with a Notte cloud browser.

The app is served from inside the sandbox and exposed on a hosted URL. A Notte
browser then opens that URL twice: once from this script with Playwright over
CDP, and once from inside the sandbox with the Notte CLI, the way an agent
running in the sandbox would.
"""

import json
import os
import shlex
from pathlib import Path

from boat_sdk import ApiClient, Configuration, exec_command, wait_until_ready, write_text
from boat_sdk.api.boat_api import BoatApi
from boat_sdk.models import CommandRequest, CreateSandboxRequest, HostPortRequest
from dotenv import load_dotenv
from notte_sdk import NotteClient

PORT = 8000
APP_DIR = "app"  # Relative to /home/user, like every boat file path.
OUTPUT_DIR = Path(__file__).parent / "output"

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


def run(boat: BoatApi, sandbox_id: str, command: str, timeout: int = 120) -> str:
    """Run a command in the sandbox and return its output, raising if it fails."""
    result = exec_command(boat, sandbox_id, command, timeout_seconds=timeout).actual_instance
    if result.exit_code != 0:
        raise CommandError(f"`{command}` exited with {result.exit_code}: {(result.stderr or result.stdout).strip()}")
    return result.stdout


def create_sandbox(boat: BoatApi) -> str:
    """Create a sandbox whose commands can call the Notte API, and wait until it is ready."""
    env = {"NOTTE_API_KEY": os.environ["NOTTE_API_KEY"]}
    if api_url := os.environ.get("NOTTE_API_URL"):
        env["NOTTE_API_URL"] = api_url
    sandbox_id = boat.create(create_sandbox_request=CreateSandboxRequest(ttl_seconds=1800, env=env)).sandbox.id
    wait_until_ready(boat, sandbox_id)
    return sandbox_id


def start_app(boat: BoatApi, sandbox_id: str) -> str:
    """Serve the app from the sandbox and return its hosted URL."""
    write_text(boat, sandbox_id, f"{APP_DIR}/index.html", APP_HTML)
    # A detached command keeps running after the call returns.
    boat.command(sandbox_id, CommandRequest(command=f"python3 -m http.server {PORT}", cwd=APP_DIR, detached=True))
    # Wait until the server accepts connections before handing the URL to the browser.
    run(
        boat,
        sandbox_id,
        f"for i in $(seq 1 50); do curl -sf http://localhost:{PORT} > /dev/null && exit 0; sleep 0.2; done; exit 1",
    )
    # The URL carries an access token, so the browser needs no auth header.
    return boat.host_port(sandbox_id, HostPortRequest(port=PORT, title="To-do app")).url


def check_with_playwright(notte: NotteClient, url: str) -> list[str]:
    """Open the app in a Notte browser from this script and return its to-dos."""
    with notte.Session() as session:
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


def install_notte(boat: BoatApi, sandbox_id: str) -> None:
    """Install the latest Notte CLI release and the Notte skill for coding agents."""
    run(boat, sandbox_id, "curl -fsSL https://notte.cc/install-cli.sh | sh")
    # Installs into ~/.agents/skills, where Claude Code, Codex and other agents pick it up.
    run(boat, sandbox_id, "notte skill add --yes", timeout=240)
    skills = run(boat, sandbox_id, "ls ~/.agents/skills").split()
    print(f"Installed the Notte CLI and skills: {', '.join(skills)}")


def check_with_notte_cli(boat: BoatApi, sandbox_id: str, url: str) -> str:
    """Drive a Notte browser from inside the sandbox with CLI commands and return the scraped page."""
    # NOTTE_API_KEY comes from the sandbox's environment, set when it was created.
    started = run(boat, sandbox_id, "notte sessions start -o json")

    # From here on the session exists, so always try to stop it.
    try:
        session = json.loads(started)
        # viewer_url is optional in the session response.
        print(f"Notte CLI started session {session['session_id']}, watch it live: {session.get('viewer_url')}")
        commands = [
            f"notte page goto {shlex.quote(url)}",
            "notte page fill '#title' 'Ship the boat example'",
            "notte page click 'button[type=submit]'",
            "notte page scrape --only-main-content",
        ]
        output = ""
        for command in commands:
            # Keep the access token in the hosted URL out of the printed output.
            print(f"$ {command.replace(url, '<hosted URL>')}")
            output = run(boat, sandbox_id, command).strip()
            print(output.replace(url, "<hosted URL>"))
        return output
    finally:
        # Stop the session even when a command fails. Warn instead of raising, so a
        # failed stop never hides the original error.
        try:
            run(boat, sandbox_id, "notte sessions stop --yes")
            print("Notte CLI session stopped")
        except CommandError as error:
            print(f"Warning: could not stop the Notte CLI session: {error}")


def main() -> None:
    load_dotenv()
    notte = NotteClient()
    config = Configuration(host="https://boat.dev/api/v1", access_token=os.environ["BOAT_API_KEY"])
    with ApiClient(config) as client:
        boat = BoatApi(client)
        sandbox_id = create_sandbox(boat)
        print(f"Created sandbox {sandbox_id}")

        try:
            url = start_app(boat, sandbox_id)
            print(f"App is live on port {PORT} at a hosted URL")
            check_with_playwright(notte, url)
            install_notte(boat, sandbox_id)
            check_with_notte_cli(boat, sandbox_id, url)
        finally:
            # Warn instead of raising, so a failed delete never hides the original error.
            try:
                boat.delete_sandbox(x_ascii_confirm_delete=sandbox_id, sandbox_id=sandbox_id)
                print("Sandbox deleted")
            except Exception as error:
                print(f"Warning: could not delete sandbox {sandbox_id}: {error}")


if __name__ == "__main__":
    main()
