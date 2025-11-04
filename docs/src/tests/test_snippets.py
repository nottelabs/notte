import io
import logging
import os
import subprocess
import tempfile
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from dotenv import load_dotenv
from notte_sdk.client import NotteClient
from pytest_examples import CodeExample, EvalExample
from pytest_examples.find_examples import _extract_code_chunks

# Fast mode: only check syntax, don't execute (for CI)
FAST_MODE = os.environ.get("DOCS_TEST_FAST_MODE", "false").lower() == "true"
# Type check mode: use mypy for type validation
TYPE_CHECK_MODE = os.environ.get("DOCS_TEST_TYPE_CHECK", "false").lower() == "true"

# Mypy error codes to suppress globally (very few!)
# Only suppress errors that affect EVERY file due to SDK design
MYPY_DISABLED_ERROR_CODES = [
    # Currently empty - we want to catch as much as possible
]

# Files with unavoidable SDK-level type issues
# These files still get type checked but with relaxed rules
FILES_WITH_SDK_TYPE_ISSUES = {
    "agents/fallback.mdx": ["call-arg"],  # AgentFallback internal _client param
    "sessions/stealth_configuration.mdx": ["call-overload"],  # **dict unpacking
    "sessions/upload_cookies_simple.mdx": ["arg-type"],  # Cookie TypedDict vs dict
    "sessions/upload_cookies.mdx": ["arg-type"],  # Cookie TypedDict vs dict
}

SNIPPETS_DIR = Path(__file__).parent.parent / "snippets"
DOCS_DIR = Path(__file__).parent.parent / "features"
CONCEPTS_DIR = Path(__file__).parent.parent / "concepts"
SDK_DIR = Path(__file__).parent.parent / "sdk-reference"

if not SDK_DIR.exists():
    raise FileNotFoundError(f"SDK directory not found: {SDK_DIR}")

if not SNIPPETS_DIR.exists():
    raise FileNotFoundError(f"Snippets directory not found: {SNIPPETS_DIR}")

if not DOCS_DIR.exists():
    raise FileNotFoundError(f"Docs directory not found: {DOCS_DIR}")


if not CONCEPTS_DIR.exists():
    raise FileNotFoundError(f"Concepts directory not found: {CONCEPTS_DIR}")


def test_no_snippets_outside_folder():
    all_docs = [
        file
        for folder in (DOCS_DIR, SDK_DIR / "manual", CONCEPTS_DIR)
        for file in folder.glob("**/*.mdx")
        if file.parent.name != "use-cases" and file.name != "bua.mdx"
    ]

    should_raise = False
    for code in find_snippets_examples(all_docs):
        should_raise = True
        logging.warning(f"Found snippet at {str(code)}")

    assert not should_raise


def find_snippets_files() -> list[Path]:
    """
    Find all Python files in the given directory, excluding __init__.py and test files.

    Args:
        directory: The directory to search in

    Returns:
        A list of Path objects for Python files
    """
    return [file for file in SNIPPETS_DIR.glob("**/*.mdx")]


def find_snippets_examples(
    sources: list[Path | io.StringIO],
) -> Generator[CodeExample, None, None]:
    for source in sources:
        group = uuid4()

        if isinstance(source, io.StringIO):
            code = source.getvalue()
        else:
            code = source.read_text("utf-8")
        yield from _extract_code_chunks(source if isinstance(source, Path) else Path(""), code, group)


handlers: dict[str, Callable[[EvalExample, str], Any]] = {}


def handle_file(filepath: str):
    def decorator(func: Callable[[EvalExample, str], Any]):
        handlers[filepath] = func

    return decorator


@handle_file("vaults/index.mdx")
def handle_vault(
    eval_example: EvalExample,
    code: str,
) -> None:
    code = code.replace("<your-mfa-secret>", "JBSWY3DPEHPK3PXP")
    run_example(eval_example, code=code)


@handle_file("agents/index.mdx")
def handle_agent(
    eval_example: EvalExample,
    code: str,
) -> None:
    run_example(eval_example, code=code)


@handle_file("personas/create_account.mdx")
def handle_create_account(
    eval_example: EvalExample,
    code: str,
) -> None:
    code = code.replace("<your-persona-id>", "23ae78af-93b4-4aeb-ba21-d18e1496bdd9")
    if FAST_MODE:
        # Just syntax check
        run_example(eval_example, code=code)
    else:
        # Skip execution in full mode to avoid opening viewer
        logging.info("Skipping create_account test (requires human interaction with open_viewer)")
        pass


@handle_file("scraping/agent.mdx")
def handle_scraping_agent(
    eval_example: EvalExample,
    code: str,
) -> None:
    code = code.replace("<your-vault-id>", "4d97be83-baf3-4c7a-a417-693e23903e70")
    run_example(eval_example, code=code)


@handle_file("vaults/manual.mdx")
def handle_vault_manual(
    eval_example: EvalExample,
    code: str,
) -> None:
    code = code.replace("<your-mfa-secret>", "JBSWY3DPEHPK3PXP").replace(
        "my_vault_id", "4d97be83-baf3-4c7a-a417-693e23903e70"
    )
    try:
        run_example(eval_example, code=code)
    except Exception as e:
        if "The vault does not exist" not in str(e):
            raise


@handle_file("workflows/fork.mdx")
def handle_workflow_fork(
    eval_example: EvalExample,
    code: str,
) -> None:
    code = code.replace("<any-public-workflow-id>", "9fb6d40e-c76a-4d44-a73a-aa7843f0f535")
    run_example(eval_example, code=code)


@handle_file("vaults/index.mdx")
def handle_vault_index(
    eval_example: EvalExample,
    code: str,
) -> None:
    _ = load_dotenv()
    notte = NotteClient()
    with notte.Vault() as vault:
        code = code.replace("<your-mfa-secret>", "JBSWY3DPEHPK3PXP").replace("my_vault_id", vault.vault_id)
        run_example(eval_example, code=code)


@handle_file("sessions/file_storage_basic.mdx")
def handle_storage_base_upload_file(
    eval_example: EvalExample,
    code: str,
) -> None:
    code = code.replace("/path/to/document.pdf", "tests/data/test.pdf")
    run_example(eval_example, code=code)


@handle_file("sessions/file_storage_upload.mdx")
def handle_storage_upload_file(
    eval_example: EvalExample,
    code: str,
) -> None:
    code = code.replace("/path/to/document.pdf", "tests/data/test.pdf")
    run_example(eval_example, code=code)


@handle_file("sessions/external_cdp.mdx")
def handle_external_cdp(
    eval_example: EvalExample,
    code: str,
) -> None:
    client = NotteClient()
    with client.Session() as session:
        cdp_url = session.cdp_url()
        code = code.replace("wss://your-external-cdp-url", cdp_url)
        run_example(eval_example, code=code)


@handle_file("sessions/upload_cookies.mdx")
def handle_cookies_file(
    eval_example: EvalExample,
    code: str,
) -> None:
    code = code.replace("path/to/cookies.json", "tests/data/cookies.json")
    run_example(eval_example, code=code, source_name="sessions/upload_cookies.mdx")


@handle_file("sessions/extract_cookies_manual.mdx")
def ignore_extract_cookies(
    _eval_example: EvalExample,
    _code: str,
) -> None:
    """Skip execution for manual cookie extraction example."""
    pass


@handle_file("sessions/solve_captchas.mdx")
def handle_solve_captchas(
    eval_example: EvalExample,
    code: str,
) -> None:
    """Skip or mock solve_captchas example with open_viewer."""
    if FAST_MODE:
        # Just syntax check
        run_example(eval_example, code=code)
    else:
        # Skip execution in full mode to avoid opening viewer
        logging.info("Skipping solve_captchas test (requires human interaction)")
        pass


@handle_file("sessions/cdp.mdx")
def handle_cdp(
    eval_example: EvalExample,
    code: str,
) -> None:
    import os
    import tempfile

    # Create a temporary file for the screenshot to avoid path issues
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        screenshot_path = tmp.name

    try:
        # Replace the screenshot path in the code
        code = code.replace("screenshot.png", screenshot_path)
        run_example(eval_example, code=code)
    finally:
        # Clean up the screenshot file if it exists
        if os.path.exists(screenshot_path):
            try:
                os.unlink(screenshot_path)
            except OSError:
                pass


def get_disabled_codes_for_file(source_path: Path) -> list[str]:
    """Get list of error codes to disable for a specific file."""
    # Get the relative path parts we care about (last 2 components)
    parts = source_path.parts[-2:] if len(source_path.parts) >= 2 else source_path.parts
    relative_path = "/".join(parts)

    # Combine global disabled codes with file-specific ones
    disabled_codes = list(MYPY_DISABLED_ERROR_CODES)
    if relative_path in FILES_WITH_SDK_TYPE_ISSUES:
        disabled_codes.extend(FILES_WITH_SDK_TYPE_ISSUES[relative_path])

    return disabled_codes


def mypy_check_code(code: str, source_name: str | Path) -> None:
    """
    Run mypy type checking on a code snippet.

    Args:
        code: The Python code to check
        source_name: Name/path for error reporting

    Raises:
        TypeError: If mypy finds type errors
    """
    # Write code to a temporary file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
        tmp.write(code)
        tmp_path = tmp.name

    try:
        # Get file-specific disabled error codes
        source_path = Path(source_name) if isinstance(source_name, str) else source_name
        disabled_codes = get_disabled_codes_for_file(source_path)

        # Build mypy command with disabled error codes
        mypy_cmd = [
            "uv",
            "run",
            "mypy",
            tmp_path,
            "--ignore-missing-imports",  # Don't fail on missing stub files
            "--no-error-summary",
            "--show-column-numbers",
            "--show-error-codes",
            "--no-pretty",  # Plain output for parsing
        ]

        # Add disabled error codes (file-specific SDK issues)
        for error_code in disabled_codes:
            mypy_cmd.append(f"--disable-error-code={error_code}")

        # Run mypy on the temporary file
        result = subprocess.run(
            mypy_cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            # Parse and format mypy errors
            errors = []
            for line in result.stdout.splitlines():
                if tmp_path in line:
                    # Replace temp path with source name
                    line = line.replace(tmp_path, str(source_name))
                    errors.append(line)

            if errors:
                error_msg = f"Type checking failed for {source_name}:\n" + "\n".join(errors)
                raise TypeError(error_msg)
    finally:
        # Clean up temp file
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def run_example(
    eval_example: EvalExample,
    path: Path | None = None,
    code: str | None = None,
    source_name: str | Path | None = None,
):
    """
    Run or validate a code example.

    Args:
        eval_example: pytest-examples eval instance
        path: Path to file to run (mutually exclusive with code)
        code: Code string to run (mutually exclusive with path)
        source_name: Optional source name for error reporting when using code string
    """
    if (path is None and code is None) or (path is not None and code is not None):
        raise ValueError("Either path or code should be provided")

    file: io.StringIO | Path
    actual_source_name: str | Path
    if path is not None:
        file = path
        actual_source_name = path
    else:
        file = io.StringIO(code)
        actual_source_name = source_name if source_name else "."

    for example in find_snippets_examples([file]):
        # Use actual source name for better error reporting
        example_source = actual_source_name if isinstance(file, io.StringIO) else example.path

        if FAST_MODE or TYPE_CHECK_MODE:
            # Fast mode: compile for syntax check
            try:
                _ = compile(example.source, f"<{example_source}>", "exec")
                logging.info(f"✓ Syntax check passed: {example_source}")
            except SyntaxError as e:
                raise SyntaxError(f"Syntax error in {example_source}: {e}")

            # Type check mode: also run mypy
            if TYPE_CHECK_MODE:
                try:
                    mypy_check_code(example.source, example_source)
                    logging.info(f"✓ Type check passed: {example_source}")
                except TypeError:
                    raise
        else:
            # Full mode: actually execute the code
            _ = eval_example.run(example)


@pytest.mark.parametrize(
    "snippet_file", find_snippets_files(), ids=lambda p: f"{p.parent.name}_{p.name.replace('.mdx', '')}"
)
def test_python_snippets(snippet_file: Path, eval_example: EvalExample):
    _ = load_dotenv()

    snippet_name = f"{snippet_file.parent.name}/{snippet_file.name}"
    custom_fn = handlers.get(snippet_name)
    try:
        if custom_fn is not None:
            custom_fn(eval_example, snippet_file.read_text("utf-8"))
        else:
            run_example(eval_example, snippet_file)
    except Exception as e:
        # Log the error and re-raise with context
        error_msg = f"Test failed for {snippet_name}: {type(e).__name__}: {str(e)}"
        logging.error(error_msg)
        # Just re-raise the original exception to avoid constructor issues with custom exception types
        raise
