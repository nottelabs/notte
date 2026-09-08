# Configuration file for the Sphinx documentation builder.
import os
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
    "notte_sdk.endpoints.agents.AgentsClient",
    "notte_sdk.endpoints.agents.RemoteAgent",
    "notte_sdk.endpoints.sessions.RemoteSession",
    "notte_sdk.endpoints.functions.NotteFunction",
    # agent fallback
    "notte_sdk.agent_fallback.RemoteAgentFallback",
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


def setup(app: Sphinx) -> None:
    _ = app.connect("build-finished", preserve_function_runtime_default)
