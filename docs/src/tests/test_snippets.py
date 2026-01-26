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
    "agents/fallback.py": ["call-arg"],  # AgentFallback internal _client param
    "sessions/stealth_configuration.py": ["call-overload"],  # **dict unpacking
    "sessions/upload_cookies_simple.py": ["arg-type"],  # Cookie TypedDict vs dict
    "sessions/upload_cookies.py": ["arg-type"],  # Cookie TypedDict vs dict
    # ProxyGeolocationCountry is accepted directly in PyPI SDK v1.8.0 but not local SDK
    "stealth/rotate_proxies.py": ["call-overload"],
    "capabilities/rotate_proxies.py": ["call-overload"],
}

SNIPPETS_DIR = Path(__file__).parent.parent / "snippets"
TESTERS_DIR = Path(__file__).parent.parent / "testers"
ROOT_DIR = Path(__file__).parent.parent

# Directories to check for inline code blocks
DOCS_DIR = ROOT_DIR / "features"
CONCEPTS_DIR = ROOT_DIR / "concepts"
SDK_DIR = ROOT_DIR / "sdk-reference"
GUIDES_DIR = ROOT_DIR / "guides"
INTEGRATIONS_DIR = ROOT_DIR / "integrations"
INTRO_DIR = ROOT_DIR / "intro"
PRODUCT_DIR = ROOT_DIR / "product"
TUTORIALS_DIR = ROOT_DIR / "tutorials"

if not SDK_DIR.exists():
    raise FileNotFoundError(f"SDK directory not found: {SDK_DIR}")

if not TESTERS_DIR.exists():
    raise FileNotFoundError(f"Testers directory not found: {TESTERS_DIR}")

if not SNIPPETS_DIR.exists():
    raise FileNotFoundError(f"Snippets directory not found: {SNIPPETS_DIR}")

if not DOCS_DIR.exists():
    raise FileNotFoundError(f"Docs directory not found: {DOCS_DIR}")

if not CONCEPTS_DIR.exists():
    raise FileNotFoundError(f"Concepts directory not found: {CONCEPTS_DIR}")


def test_no_snippets_outside_folder():
    # Directories to check for inline code blocks
    # Note: sdk-reference/ is excluded as it's auto-generated API docs
    folders_to_check = [
        DOCS_DIR,  # features/
        CONCEPTS_DIR,  # concepts/
        GUIDES_DIR,  # guides/
        INTEGRATIONS_DIR,  # integrations/
        INTRO_DIR,  # intro/
        PRODUCT_DIR,  # product/
        TUTORIALS_DIR,  # tutorials/
    ]

    # Files that intentionally use CodeGroup (Python/JS tabs) or are comment-only
    # These are excluded from the inline code check
    files_with_codegroup_or_manual = {
        "browser-types.mdx",  # All CodeGroup wrappers (Python/JS/Bash tabs)
        "captcha-solving.mdx",  # CodeGroup wrappers for multi-language
        "stealth-mode.mdx",  # CodeGroup wrappers for multi-language
        "kernel.mdx",  # Integration-specific examples
        "schedules.mdx",  # Comment-only cron examples
        "management.mdx",  # Comment-only metadata example
        "quickstart.mdx",  # CodeGroup with Python/JS tabs
        "lifecycle.mdx",  # CodeGroup wrappers
        "configuration.mdx",  # CodeGroup wrappers
        "playwright-vs-notte.mdx",  # CodeGroup wrappers
        "external-providers.mdx",  # CodeGroup wrappers
        "playwright.mdx",  # CodeGroup wrappers (in sessions/cdp)
        "puppeteer.mdx",  # CodeGroup wrappers
        "selenium.mdx",  # CodeGroup wrappers
    }

    # Collect all MDX files from directories
    all_docs = []
    for folder in folders_to_check:
        if folder.exists():
            all_docs.extend(
                file
                for file in folder.glob("**/*.mdx")
                if file.parent.name != "use-cases"
                and file.name != "bua.mdx"
                and file.name not in files_with_codegroup_or_manual
            )

    # Also check root-level MDX files (excluding migration-plan.mdx and other meta files)
    root_mdx_files = [
        f
        for f in ROOT_DIR.glob("*.mdx")
        if f.name not in ("migration-plan.mdx", "zin.mdx") and f.name not in files_with_codegroup_or_manual
    ]
    all_docs.extend(root_mdx_files)

    should_raise = False
    for code in find_snippets_examples(all_docs):
        should_raise = True
        logging.warning(f"Found snippet at {str(code)}")

    assert not should_raise


def find_tester_files() -> list[Path]:
    """
    Find all Python tester files in the testers directory.

    Returns:
        A list of Path objects for Python tester files
    """
    return [file for file in TESTERS_DIR.glob("**/*.py") if file.name != "__init__.py"]


def find_snippets_files() -> list[Path]:
    """
    Find all MDX snippet files in the snippets directory.

    Returns:
        A list of Path objects for MDX snippet files
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


@handle_file("vaults/index.py")
def handle_vault(
    eval_example: EvalExample,
    code: str,
) -> None:
    code = code.replace("<your-mfa-secret>", "JBSWY3DPEHPK3PXP")
    run_example(eval_example, code=code)


@handle_file("agents/index.py")
def handle_agent(
    eval_example: EvalExample,
    code: str,
) -> None:
    run_example(eval_example, code=code)


@handle_file("personas/create_account.py")
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


@handle_file("scraping/agent.py")
def handle_scraping_agent(
    eval_example: EvalExample,
    code: str,
) -> None:
    code = code.replace("<your-vault-id>", "4d97be83-baf3-4c7a-a417-693e23903e70")
    run_example(eval_example, code=code)


@handle_file("vaults/manual.py")
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


@handle_file("workflows/fork.py")
def handle_workflow_fork(
    eval_example: EvalExample,
    code: str,
) -> None:
    code = code.replace("<any-public-workflow-id>", "9fb6d40e-c76a-4d44-a73a-aa7843f0f535")
    run_example(eval_example, code=code)


@handle_file("vaults/index.py")
def handle_vault_index(
    eval_example: EvalExample,
    code: str,
) -> None:
    if FAST_MODE or TYPE_CHECK_MODE:
        # Syntax/type check - don't create client
        code = code.replace("<your-mfa-secret>", "JBSWY3DPEHPK3PXP").replace("my_vault_id", "placeholder-vault-id")
        run_example(eval_example, code=code)
    else:
        # Full mode: create real vault
        _ = load_dotenv()
        client = NotteClient()
        with client.Vault() as vault:
            code = code.replace("<your-mfa-secret>", "JBSWY3DPEHPK3PXP").replace("my_vault_id", vault.vault_id)
            run_example(eval_example, code=code)


@handle_file("sessions/file_storage_basic.py")
def handle_storage_base_upload_file(
    eval_example: EvalExample,
    code: str,
) -> None:
    code = code.replace("/path/to/document.pdf", "tests/data/test.pdf")
    run_example(eval_example, code=code)


@handle_file("sessions/file_storage_upload.py")
def handle_storage_upload_file(
    eval_example: EvalExample,
    code: str,
) -> None:
    code = code.replace("/path/to/document.pdf", "tests/data/test.pdf")
    run_example(eval_example, code=code)


@handle_file("sessions/external_cdp.py")
def handle_external_cdp(
    eval_example: EvalExample,
    code: str,
) -> None:
    if FAST_MODE or TYPE_CHECK_MODE:
        # Syntax/type check - don't create client or session
        code = code.replace("wss://your-external-cdp-url", "wss://placeholder-cdp-url")
        run_example(eval_example, code=code)
    else:
        client = NotteClient()
        with client.Session() as session:
            cdp_url = session.cdp_url()
            code = code.replace("wss://your-external-cdp-url", cdp_url)
            run_example(eval_example, code=code)


@handle_file("sessions/upload_cookies.py")
def handle_cookies_file(
    eval_example: EvalExample,
    code: str,
) -> None:
    code = code.replace("path/to/cookies.json", "tests/data/cookies.json")
    run_example(eval_example, code=code, source_name="sessions/upload_cookies.py")


@handle_file("sessions/extract_cookies_manual.py")
def ignore_extract_cookies(
    _eval_example: EvalExample,
    _code: str,
) -> None:
    """Skip execution for manual cookie extraction example."""
    pass


@handle_file("sessions/solve_captchas.py")
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


@handle_file("sessions/cdp.py")
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


def strip_sniptest_comments(code: str) -> str:
    """
    Strip # @sniptest comments from code.

    These are magic comments used for snippet generation and should be
    removed before syntax checking or execution.
    """
    lines = code.split("\n")
    filtered = [line for line in lines if not line.strip().startswith("# @sniptest")]
    return "\n".join(filtered)


def run_example(
    eval_example: EvalExample,
    path: Path | None = None,
    code: str | None = None,
    source_name: str | Path | None = None,
):
    """
    Run or validate a code example (Python file or code string).

    Args:
        eval_example: pytest-examples eval instance
        path: Path to Python file to run (mutually exclusive with code)
        code: Code string to run (mutually exclusive with path)
        source_name: Optional source name for error reporting when using code string
    """
    if (path is None and code is None) or (path is not None and code is not None):
        raise ValueError("Either path or code should be provided")

    if path is not None:
        source_code = path.read_text("utf-8")
        actual_source_name = path
    else:
        source_code = code  # type: ignore
        actual_source_name = source_name if source_name else "<code>"

    # Strip sniptest magic comments before processing
    source_code = strip_sniptest_comments(source_code)

    if FAST_MODE or TYPE_CHECK_MODE:
        # Fast mode: compile for syntax check
        try:
            _ = compile(source_code, f"<{actual_source_name}>", "exec")
            logging.info(f"✓ Syntax check passed: {actual_source_name}")
        except SyntaxError as e:
            raise SyntaxError(f"Syntax error in {actual_source_name}: {e}")

        # Type check mode: also run mypy
        if TYPE_CHECK_MODE:
            try:
                mypy_check_code(source_code, actual_source_name)
                logging.info(f"✓ Type check passed: {actual_source_name}")
            except TypeError:
                raise
    else:
        # Full mode: actually execute the code using pytest-examples
        file = io.StringIO(source_code)
        for example in find_snippets_examples([file]):
            _ = eval_example.run(example)


@pytest.mark.parametrize(
    "tester_file", find_tester_files(), ids=lambda p: f"{p.parent.name}_{p.name.replace('.py', '')}"
)
def test_python_testers(tester_file: Path, eval_example: EvalExample):
    """
    Test all Python tester files in /testers/.

    Testers are the source of truth for code snippets. They contain
    actual runnable Python code with # @sniptest magic comments.
    """
    _ = load_dotenv()

    tester_name = f"{tester_file.parent.name}/{tester_file.name}"
    custom_fn = handlers.get(tester_name)
    try:
        if custom_fn is not None:
            custom_fn(eval_example, tester_file.read_text("utf-8"))
        else:
            run_example(eval_example, tester_file)
    except Exception as e:
        # Log the error and re-raise with context
        error_msg = f"Test failed for {tester_name}: {type(e).__name__}: {str(e)}"
        logging.error(error_msg)
        raise


def test_snippets_are_autogenerated():
    """
    Verify all snippets in /snippets/ are auto-generated by sniptest.

    Auto-generated snippets have a header comment:
    {/* @sniptest testers/path/to/file.py */}

    Exceptions:
    - CodeGroup-wrapped snippets (multi-language) are manual and exempt
    """
    import re

    sniptest_pattern = re.compile(r"\{/\*\s*@sniptest\s+testers/")

    for snippet_file in find_snippets_files():
        content = snippet_file.read_text("utf-8")

        # Skip CodeGroup-wrapped snippets (multi-language, manually maintained)
        if content.strip().startswith("<CodeGroup>"):
            continue

        if not sniptest_pattern.search(content):
            pytest.fail(
                f"Snippet {snippet_file} is not auto-generated by sniptest. "
                f"All snippets must be generated from /testers/*.py files. "
                f"Run 'python sniptest/generate.py' to regenerate."
            )
