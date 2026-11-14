"""Test a web app running on a boxd machine with a Notte cloud browser.

The app is served from inside the machine on the machine's HTTPS URL. A Notte
browser then opens that URL twice: once from this script with Playwright over
CDP, and once from inside the machine with the Notte CLI, the way an agent
running on the machine would.
"""

import json
import os
import re
import shlex
from pathlib import Path
from uuid import uuid4

from boxd import Boxd, Machine
from dotenv import load_dotenv
from notte_sdk import NotteClient

PORT = 8000  # The machine's HTTPS URL forwards to this port.
DELETE_AFTER_SECONDS = 1800  # boxd deletes the machine after 30 minutes, also when this script dies.
APP_DIR = "/home/boxd/app"
OUTPUT_DIR = Path(__file__).parent / "output"
TODOS = ["Write the app", "Start the server"]  # The to-dos the app starts with.
NEW_TODO = "Ship the boxd example"  # The to-do the Notte CLI adds.

# A small to-do app, standing in for whatever your agent builds on the machine.
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
    """A command on the machine exited with a non-zero code."""


class CheckError(RuntimeError):
    """A browser did not see the app as expected."""


def notte_env() -> dict[str, str]:
    """The environment the Notte CLI needs on the machine."""
    env = {"NOTTE_API_KEY": os.environ["NOTTE_API_KEY"]}
    if api_url := os.environ.get("NOTTE_API_URL"):
        env["NOTTE_API_URL"] = api_url
    return env


def run(
    boxd: Boxd,
    machine_id: str,
    command: str,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    timeout: int = 120,
) -> str:
    """Run a command on the machine and return its output, raising if it fails."""
    result = boxd.machines.exec(machine_id, command, env=env, cwd=cwd, timeout=timeout)
    if result.exit_code != 0:
        raise CommandError(f"`{command}` exited with {result.exit_code}: {str(result.stderr or result.stdout).strip()}")
    return str(result.stdout)


def delete_machine(boxd: Boxd, machine_id: str) -> bool:
    """Delete the machine and return whether that worked.

    Warn instead of raising, so a failed delete never hides an earlier error.
    """
    try:
        boxd.machines.delete(machine_id)
    except Exception as error:
        print(f"Warning: could not delete machine {machine_id}: {error}")
        return False
    print("Machine deleted")
    return True


def create_machine(boxd: Boxd) -> Machine:
    """Create a machine and wait until it accepts commands."""
    prefix = os.environ.get("BOXD_MACHINE_PREFIX", "notte-example-")
    # An isolated machine has no network path to your other machines, a safe default for agent code.
    machine = boxd.machines.create(
        f"{prefix}{uuid4().hex[:8]}",
        org=os.environ.get("BOXD_ORG"),
        isolated=True,
        delete_after=DELETE_AFTER_SECONDS,
    )
    try:
        machine = boxd.machines.wait_until_ready(machine.id)
        # Bot protection shows visitors a browser check first; this app has nothing to protect.
        boxd.machines.set_bot_protection(machine.id, mode="off")
    except BaseException:
        # The caller only deletes machines it gets back, so delete this one here,
        # also when the wait is interrupted with Ctrl-C.
        delete_machine(boxd, machine.id)
        raise
    print(f"Created machine {machine.name} ({machine.id})")
    return machine


def start_app(boxd: Boxd, machine: Machine) -> str:
    """Serve the app from the machine and return its HTTPS URL."""
    boxd.machines.files.upload(machine.id, f"{APP_DIR}/index.html", APP_HTML)
    # nohup and & keep the server running after the command returns.
    run(boxd, machine.id, f"nohup python3 -m http.server {PORT} > /tmp/app.log 2>&1 &", cwd=APP_DIR, timeout=30)
    # Wait until the server accepts connections before handing the URL to the browser.
    run(
        boxd,
        machine.id,
        f"for i in $(seq 1 50); do curl -sf http://localhost:{PORT} > /dev/null && exit 0; sleep 0.2; done; exit 1",
    )
    return machine.access.url


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


def install_notte(boxd: Boxd, machine_id: str) -> None:
    """Install the latest Notte CLI release and the Notte skill for coding agents."""
    run(boxd, machine_id, "curl -fsSL https://notte.cc/install-cli.sh | sh")
    # Installs into ~/.agents/skills, where Claude Code, Codex and other agents pick it up.
    run(boxd, machine_id, "notte skill add --yes", timeout=240)
    skills = run(boxd, machine_id, "ls ~/.agents/skills").split()
    print(f"Installed the Notte CLI and skills: {', '.join(skills)}")


def check_with_notte_cli(boxd: Boxd, machine_id: str, url: str) -> str:
    """Drive a Notte browser from inside the machine with CLI commands and return the scraped page."""
    # The Notte key goes with each command, so it is never stored on the machine.
    env = notte_env()
    # The start command can create the session and still fail, so always try to stop it.
    try:
        started = run(boxd, machine_id, "notte sessions start -o json", env=env)
        session = json.loads(started)
        # viewer_url is optional in the session response.
        print(f"Notte CLI started session {session['session_id']}, watch it live: {session.get('viewer_url')}")
        commands = [
            f"notte page goto {shlex.quote(url)}",
            f"notte page fill '#title' {shlex.quote(NEW_TODO)}",
            "notte page click 'button[type=submit]'",
            "notte page scrape --only-main-content",
        ]
        output = ""
        for command in commands:
            print(f"$ {command}")
            output = run(boxd, machine_id, command, env=env).strip()
            print(output)
        return output
    finally:
        # Stop the session even when a command fails. Warn instead of raising, so a
        # failed stop never hides the original error.
        try:
            run(boxd, machine_id, "notte sessions stop --yes", env=env)
            print("Notte CLI session stopped")
        except Exception as error:
            print(f"Warning: could not stop the Notte CLI session: {error}")


def expect_todos(todos: list[str]) -> None:
    """Raise unless Playwright read the to-dos the app starts with."""
    if todos != TODOS:
        raise CheckError(f"Playwright saw the to-dos {todos}, expected {TODOS}")


def expect_new_todo(page: str) -> None:
    """Raise unless the page the Notte CLI scraped shows the added to-do and the new count."""
    # The CLI wraps long lines at spaces and hyphens, so join them again before comparing.
    seen = re.sub(r"-\s+", "-", " ".join(page.split()))
    count = f"{len(TODOS) + 1} to-dos"
    if NEW_TODO not in seen:
        raise CheckError(f"The Notte CLI did not see '{NEW_TODO}' on the page: {page}")
    if not re.search(rf"(?<!\d){re.escape(count)}", seen):
        raise CheckError(f"The Notte CLI did not see '{count}' on the page: {page}")


def main() -> None:
    load_dotenv()
    notte = NotteClient()
    boxd = Boxd()
    machine = create_machine(boxd)

    try:
        url = start_app(boxd, machine)
        print(f"App is live on port {PORT} at {url}")
        expect_todos(check_with_playwright(notte, url))
        install_notte(boxd, machine.id)
        expect_new_todo(check_with_notte_cli(boxd, machine.id, url))
        print("Both browsers saw the app")
    finally:
        # An error from the run above passes through here, also when the delete fails.
        deleted = delete_machine(boxd, machine.id)
    if not deleted:
        raise SystemExit(
            f"Machine {machine.id} was not deleted. Delete it yourself, or boxd deletes it "
            f"{DELETE_AFTER_SECONDS // 60} minutes after it was created."
        )


if __name__ == "__main__":
    main()
