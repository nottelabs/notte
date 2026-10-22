# Configuration file for the Sphinx documentation builder.
import os
import re
import sys
from pathlib import Path

from sphinx.application import Sphinx

sys.path.insert(0, os.path.abspath(".."))  # Add parent directory to Python path
sys.path.insert(0, os.path.abspath("../.."))  # Add parent directory to Python path

# -- Project information -----------------------------------------------------
project = "Notte SDK"
copyright = "2024"
author = "Author"

# -- General configuration ---------------------------------------------------
extensions = ["sphinx.ext.autodoc", "sphinx.ext.napoleon", "sphinx_mintlify"]

# -- Options for Mintlify output ---------------------------------------------
mintlify_frontmatter = {"title": "API Reference", "description": "API documentation"}

classmd_output_dir = "src/sdk-reference"
classmd_classes = [
    # Example: Document a single class
    "notte_sdk.client.NotteClient",
    "notte_sdk.endpoints.sessions.RemoteSession",
    "notte_sdk.endpoints.functions.NotteFunction",
    # tooling
    "notte_sdk.endpoints.vaults.NotteVault",
    "notte_sdk.endpoints.personas.NottePersona",
    "notte_sdk.endpoints.files.RemoteFileStorage",
]


# -- General configuration ---------------------------------------------------
source_suffix = ".rst"
master_doc = "index"

# Ensure the builder is registered
builders = {"mintlify": "sphinx_mintlify.MintlifyBuilder"}

# -- autodoc configuration -------------------------------------------------
autodoc_member_order = "bysource"
autodoc_typehints = "description"
autodoc_class_signature = "mixed"


# sphinx-mintlify renders defaults of string type aliases without their quotes.
# Keep the public function signature valid Python after each regeneration.
def preserve_function_runtime_default(app: Sphinx, exception: Exception | None) -> None:
    if exception is not None:
        return
    reference = Path(app.confdir).parent / "src/sdk-reference/misc/nottefunction.mdx"
    if reference.exists():
        content = reference.read_text()
        _ = reference.write_text(
            content.replace("runtime: FunctionRuntime = standard", 'runtime: FunctionRuntime = "standard"')
        )

    session_reference = Path(app.confdir).parent / "src/sdk-reference/misc/remotesession.mdx"
    if session_reference.exists():
        content = session_reference.read_text()
        _ = session_reference.write_text(
            content.replace(
                "start(tries: <class 'int'> = 3, wait_for_authentication:",
                "start(tries: <class 'int'> = 3, *, wait_for_authentication:",
            )
        )

    # The upstream schema has no description for this newly exposed nested type.
    payload_reference = Path(app.confdir).parent / "src/sdk-reference/misc/runpayloadreference.mdx"
    if payload_reference.exists():
        _ = payload_reference.write_text(
            payload_reference.read_text().replace(
                'description: ""',
                'description: "Identifies an uploaded run field by its size, checksum, and upload ID."',
            )
        )


def setup(app: Sphinx) -> None:
    _ = app.connect("build-finished", preserve_function_runtime_default)
    _ = app.connect("build-finished", curate_reference)


def curate_reference(app: Sphinx, exception: Exception | None) -> None:
    """Keep generated reference pages focused on supported user operations."""
    if exception is not None:
        return
    reference = Path(app.confdir).parent / "src/sdk-reference"
    replacements = {
        "/sdk-reference/misc/basemodel": "https://docs.pydantic.dev/latest/api/base_model/",
        "/sdk-reference/misc/rootmodel": "https://docs.pydantic.dev/latest/api/root_model/",
        "/sdk-reference/nottepersona/start": "/sdk-reference/manual/persona",
        "/sdk-reference/nottepersona/stop": "/sdk-reference/manual/persona",
        "/sdk-reference/nottevault/start": "/sdk-reference/manual/vault",
        "/sdk-reference/nottevault/stop": "/sdk-reference/manual/vault",
    }
    retired = {reference / (path.removeprefix("/sdk-reference/") + ".mdx") for path in replacements}
    retired.update((reference / "agentsclient").glob("*.mdx"))
    for page in reference.rglob("*.mdx"):
        if page in retired:
            page.unlink()
            continue
        text = page.read_text()
        # Inherited lifecycle no-ops are not useful cards in the public overview.
        text = re.sub(
            r'(?:<Visibility[^>]*>\s*)?<Card\b[^>]*href="/sdk-reference/(?:nottepersona|nottevault)/(?:start|stop)(?:\.md)?"[^>]*>.*?</Card>(?:\s*</Visibility>)?',
            "",
            text,
            flags=re.DOTALL,
        )
        for old, new in replacements.items():
            for suffix in (".md", ""):
                target = new if new.startswith("https://") else new + suffix
                text = text.replace(f"]({old}{suffix})", f"]({target})")
        text = re.sub(r'/sdk-reference/agentsclient/[\w_]+(?:\.md)?(?=["\)])', "/sdk-reference/manual/agent", text)
        # Inherited pydantic docstrings link relative to their own docs site.
        text = re.sub(r"\]\(\.\./([\w/-]+)\.md(#[\w-]+)?\)", r"](https://docs.pydantic.dev/latest/\1/\2)", text)
        _ = page.write_text(text)
