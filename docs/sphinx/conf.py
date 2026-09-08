# Configuration file for the Sphinx documentation builder.
import os
import sys

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


def setup(app):
    # sphinx-mintlify keys generated type pages by bare class name. Following
    # Playwright's Page graph would overwrite requests.Response with its own
    # unrelated Response type, so link Page to its upstream reference instead.
    from sphinx_mintlify.builder import MintlifyBuilder
    from sphinx_mintlify.generator import ClassMarkdownGenerator

    class SDKReferenceGenerator(ClassMarkdownGenerator):
        def _format_type_with_links(self, annotation, module=None):
            resolved = self._resolve_type(annotation, module) if isinstance(annotation, str) else annotation
            if (
                isinstance(resolved, type)
                and resolved.__module__.startswith("playwright.")
                and resolved.__name__ == "Page"
            ):
                return "[`Page`](https://playwright.dev/python/docs/api/class-page)"
            return super()._format_type_with_links(annotation, module)

    def use_sdk_generator(app):
        if isinstance(app.builder, MintlifyBuilder):
            app.builder.generator = SDKReferenceGenerator(app)

    app.connect("builder-inited", use_sdk_generator)
