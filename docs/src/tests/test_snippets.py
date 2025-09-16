import io
import logging
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
    run_example(eval_example, code=code)


@handle_file("personas/create_account.mdx")
def handle_create_account(
    eval_example: EvalExample,
    code: str,
) -> None:
    client = NotteClient()
    persona = client.Persona("23ae78af-93b4-4aeb-ba21-d18e1496bdd9")
    persona.vault.delete_credentials(url="https://console.notte.cc")
    code = code.replace("<your-persona-id>", "23ae78af-93b4-4aeb-ba21-d18e1496bdd9")
    run_example(eval_example, code=code)


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
