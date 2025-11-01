from __future__ import annotations

import inspect
import sys
from pathlib import Path

from dotenv import load_dotenv


#There was a clash with the local session.py file and the virtual env file 

def _bootstrap_local_packages() -> None:
    """Ensure we import local Notte packages instead of the virtualenv wheels."""

    current = Path(__file__).resolve().parent
    repo_root = current
    for candidate in [current, *current.parents]:
        if (candidate / "packages").is_dir() and (candidate / "pyproject.toml").is_file():
            repo_root = candidate
            break

    packages_root = repo_root / "packages"
    candidate_paths = [
        repo_root / "src",
        packages_root / "notte-core" / "src",
        packages_root / "notte-browser" / "src",
        packages_root / "notte-agent" / "src",
        packages_root / "notte-llm" / "src",
        packages_root / "notte-sdk" / "src",
    ]

    for path in candidate_paths:
        if path.exists():
            path_str = str(path)
            if path_str not in sys.path:
                sys.path.insert(0, path_str)

    # Drop any previously imported notte modules so the interpreter reloads from the local paths
    for name in list(sys.modules.keys()):
        if name.startswith(("notte_browser", "notte_core", "notte_agent", "notte_llm", "notte_sdk", "notte")):
            sys.modules.pop(name, None)


_bootstrap_local_packages()

import notte  


def main() -> None:
    load_dotenv()

    with notte.Session(headless=False) as session:
        agent = notte.Agent(session=session, reasoning_model="gemini/gemini-2.5-flash", max_steps=30)
        response = agent.run(task="go to google and search for am and select the second dropdown suggestion")

    print(f"\n(session.py in use: {inspect.getfile(notte.Session)})")
    # status_icon = "✅" if response.success else "❌"
    # print("\n=== Agent Run Summary ===")
    # print(f"{status_icon} Success: {response.success}")
    # print(f"⌛ Duration: {response.duration_in_s:.1f}s | Steps: {len(response.steps)}")
    # print(f"🧠 Answer: {response.answer}")
    # print(f"\n(session.py in use: {inspect.getfile(notte.Session)})")


if __name__ == "__main__":
    main()
