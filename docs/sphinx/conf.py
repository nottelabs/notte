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
    "notte_sdk.endpoints.workflows.RemoteWorkflow",
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
