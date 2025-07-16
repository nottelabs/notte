import io
import logging
import re
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from dotenv import load_dotenv
from notte_sdk.client import NotteClient
from pytest_examples import CodeExample, EvalExample
from pytest_examples.find_examples import _extract_code_chunks

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
    # code = code.replace("agent = notte.Agent()", "agent = notte.Agent(raise_on_existing_contextual_session=False)")
    run_example(eval_example, code=code)


@handle_file("scraping/agent.mdx")
def handle_scraping_agent(
    eval_example: EvalExample,
    code: str,
) -> None:
    code = code.replace("<your-vault-id>", "8c618111-1d01-4e54-842a-6cac98ef4838")
    run_example(eval_example, code=code)


@handle_file("vaults/manual.mdx")
def handle_vault_manual(
    eval_example: EvalExample,
    code: str,
) -> None:
    code = code.replace("<your-mfa-secret>", "JBSWY3DPEHPK3PXP").replace(
        "my_vault_id", "8c618111-1d01-4e54-842a-6cac98ef4838"
    )
    try:
        run_example(eval_example, code=code)
    except Exception as e:
        if "The vault does not exist" not in str(e):
            raise


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


@handle_file("sessions/upload_cookies.mdx")
def handle_cookies_file(
    eval_example: EvalExample,
    code: str,
) -> None:
    code = code.replace("path/to/cookies.json", "tests/data/cookies.json")
    run_example(eval_example, code=code)


@handle_file("sessions/extract_cookies_manual.mdx")
def ignore_extract_cookies(
    eval_example: EvalExample,
    code: str,
) -> None:
    pass


def run_example(
    eval_example: EvalExample,
    path: Path | None = None,
    code: str | None = None,
):
    if (path is None and code is None) or (path is not None and code is not None):
        raise ValueError("Either path or code should be provided")

    file: io.StringIO | Path
    if path is not None:
        file = path
    else:
        file = io.StringIO(code)

    for example in find_snippets_examples([file]):
        _ = eval_example.run(example)


@pytest.mark.parametrize(
    "snippet_file", find_snippets_files(), ids=lambda p: f"{p.parent.name}_{p.name.replace('.mdx', '')}"
)
def test_python_snippets(snippet_file: Path, eval_example: EvalExample):
    _ = load_dotenv()

    snippet_name = f"{snippet_file.parent.name}/{snippet_file.name}"
    custom_fn = handlers.get(snippet_name)
    if custom_fn is not None:
        custom_fn(eval_example, snippet_file.read_text("utf-8"))
    else:
        run_example(eval_example, snippet_file)


def extract_param_fields(content: str) -> list[str]:
    """
    Extract ParamField blocks from MDX content and normalize them for comparison.
    Returns a list of normalized parameter field strings.
    """
    # Find all ParamField blocks
    param_pattern = r'<ParamField[^>]*path="([^"]*)"[^>]*type="([^"]*)"[^>]*>(.*?)</ParamField>'
    matches = re.findall(param_pattern, content, re.DOTALL | re.MULTILINE)

    normalized_params = []
    for path, type_str, description in matches:
        # Normalize the description by stripping whitespace and removing extra spaces
        desc_clean = re.sub(r"\s+", " ", description.strip())
        normalized_params.append(f"{path}|{type_str}|{desc_clean}")

    return sorted(normalized_params)


def test_agent_parameters_in_sync():
    """
    Test that parameters in sdk/manual/agent.mdx are synchronized with
    the source parameters in sdk/remoteagentfactory/__call__.mdx
    """
    agent_file = SDK_DIR / "manual" / "agent.mdx"
    factory_file = SDK_DIR / "remoteagentfactory" / "__call__.mdx"

    assert agent_file.exists(), f"Agent file not found: {agent_file}"
    assert factory_file.exists(), f"Factory file not found: {factory_file}"

    agent_content = agent_file.read_text("utf-8")
    factory_content = factory_file.read_text("utf-8")

    # Extract parameter sections from both files
    agent_params = extract_param_fields(agent_content)
    factory_params = extract_param_fields(factory_content)

    # Compare the normalized parameter lists
    missing_in_agent = set(factory_params) - set(agent_params)
    extra_in_agent = set(agent_params) - set(factory_params)

    error_messages = []
    if missing_in_agent:
        error_messages.append(f"Parameters missing in agent.mdx: {missing_in_agent}")
    if extra_in_agent:
        error_messages.append(f"Extra parameters in agent.mdx: {extra_in_agent}")

    if error_messages:
        pytest.fail(
            f"Parameter synchronization failed between {agent_file} and {factory_file}:\n" + "\n".join(error_messages)
        )


def test_session_parameters_in_sync():
    """
    Test that parameters in sdk/manual/session.mdx are synchronized with
    the source parameters in sdk/remotesessionfactory/__call__.mdx
    """
    session_file = SDK_DIR / "manual" / "session.mdx"
    factory_file = SDK_DIR / "remotesessionfactory" / "__call__.mdx"

    assert session_file.exists(), f"Session file not found: {session_file}"
    assert factory_file.exists(), f"Factory file not found: {factory_file}"

    session_content = session_file.read_text("utf-8")
    factory_content = factory_file.read_text("utf-8")

    # Extract parameter sections from both files
    session_params = extract_param_fields(session_content)
    factory_params = extract_param_fields(factory_content)

    # Compare the normalized parameter lists
    missing_in_session = set(factory_params) - set(session_params)
    extra_in_session = set(session_params) - set(factory_params)

    error_messages = []
    if missing_in_session:
        error_messages.append(f"Parameters missing in session.mdx: {missing_in_session}")
    if extra_in_session:
        error_messages.append(f"Extra parameters in session.mdx: {extra_in_session}")

    if error_messages:
        pytest.fail(
            f"Parameter synchronization failed between {session_file} and {factory_file}:\n" + "\n".join(error_messages)
        )
