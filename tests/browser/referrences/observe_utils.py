import functools
import http.server
import json
import socketserver
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Final, Iterator

from notte_browser.session import NotteSession

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------

_REF_DIR: Final[Path] = Path(__file__).parent
_HTML_DIR: Final[Path] = _REF_DIR / "browser_snapshot"
_JSON_DIR: Final[Path] = _REF_DIR / "json_snapshot"
_JSON_DIR.mkdir(parents=True, exist_ok=True)

__all__ = [
    "generate_json_snapshot",
    "update_json_snapshot",
    "start_local_html_server",
    "VIEWPORT_WIDTH",
    "VIEWPORT_HEIGHT",
    "check_data_snapshot",
    "verify_data_snapshots",
]

# -----------------------------------------------------------------------------
# Default viewport size (shared across snapshots & tests)
# -----------------------------------------------------------------------------

VIEWPORT_WIDTH: Final[int] = 1280
VIEWPORT_HEIGHT: Final[int] = 1080

# -----------------------------------------------------------------------------
# Public helpers
# -----------------------------------------------------------------------------


def generate_json_snapshot(base_server_url: str) -> list[Path]:
    """Generate JSON reference files for every HTML snapshot found.

    Parameters
    ----------
    base_server_url:
        Base URL of the running local HTML server, e.g. ``http://127.0.0.1:54321``.

    Returns
    -------
    list[Path]
        Paths to the JSON files that were (re)generated.
    """
    generated_paths: list[Path] = []

    for html_file in sorted(_HTML_DIR.glob("*.html")):
        name = html_file.stem  # "allrecipes" for "allrecipes.html"
        url = f"{base_server_url}/{html_file.name}"

        # Create a fresh Notte session for each page to avoid side-effects.
        with NotteSession(
            headless=True,
            enable_perception=False,
            viewport_width=VIEWPORT_WIDTH,
            viewport_height=VIEWPORT_HEIGHT,
        ) as session:  # type: ignore[arg-type]
            _ = session.observe(url=url)

            nodes_dump = _dump_interaction_nodes(session)

        json_path = _JSON_DIR / f"{name}.json"
        with json_path.open("w", encoding="utf-8") as fp:
            json.dump(nodes_dump, fp, indent=2, ensure_ascii=False)

        generated_paths.append(json_path)

    return generated_paths


# -----------------------------------------------------------------------------
# Convenience entry-point (auto-starts a temporary server)
# -----------------------------------------------------------------------------


@contextmanager
def start_local_html_server() -> Iterator[str]:  # pragma: no cover
    """Spin up a lightweight HTTP server serving ``_HTML_DIR`` for the duration
    of the context and yield its base URL.
    """

    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler,
        directory=str(_HTML_DIR),
    )

    httpd: socketserver.TCPServer = socketserver.TCPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]

    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


def update_json_snapshot() -> list[Path]:  # pragma: no cover
    """Generate JSON snapshots by automatically starting a temporary server.

    Call this function from a script or CI job whenever you want to refresh all
    JSON reference files without having to run pytest or start the server
    manually.
    """

    # Remove existing JSON and PNG snapshots so the output matches the current
    # set of HTML files exactly.
    for json_file in _JSON_DIR.glob("*.json"):
        try:
            json_file.unlink()
        except FileNotFoundError:
            pass

    with start_local_html_server() as url:
        return generate_json_snapshot(url)


# -----------------------------------------------------------------------------
# Validation helpers
# -----------------------------------------------------------------------------


def _dump_interaction_nodes(session: "NotteSession") -> list[dict[str, object]]:
    """Return the serialised interaction nodes for the current session."""
    nodes_dump: list[dict[str, object]] = []
    for node in session.snapshot.interaction_nodes():
        selectors: list[str] = []
        if node.computed_attributes.selectors is not None:
            selectors = node.computed_attributes.selectors.selectors()

        nodes_dump.append(
            {
                "id": node.id,
                "role": node.get_role_str(),
                "text": node.text,
                "selectors": selectors,
            }
        )

    return nodes_dump


def check_data_snapshot(base_server_url: str) -> list[str]:
    """Compare actual nodes extracted from each HTML page against stored JSON.

    Returns a list of names that did *not* match. Empty list means everything
    is consistent.
    """

    mismatches: list[str] = []

    for html_file in sorted(_HTML_DIR.glob("*.html")):
        name = html_file.stem
        url = f"{base_server_url}/{html_file.name}"

        json_path = _JSON_DIR / f"{name}.json"
        if not json_path.exists():
            mismatches.append(name)
            continue

        with NotteSession(
            headless=True,
            enable_perception=False,
            viewport_width=VIEWPORT_WIDTH,
            viewport_height=VIEWPORT_HEIGHT,
        ) as session:  # type: ignore[arg-type]
            _ = session.observe(url=url)

            actual = _dump_interaction_nodes(session)

        expected = json.loads(json_path.read_text(encoding="utf-8"))

        if actual != expected:
            mismatches.append(name)

    return mismatches


def verify_data_snapshots(base_server_url: str) -> None:
    """Assert that all stored JSON snapshots are up-to-date."""

    mismatches = check_data_snapshot(base_server_url)
    if mismatches:
        raise AssertionError("Data snapshot mismatch for: " + ", ".join(mismatches))
