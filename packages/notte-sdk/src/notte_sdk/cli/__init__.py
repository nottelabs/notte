"""
Main CLI module for Notte.

This module aggregates all CLI subcommands (workflow, session, agent, etc.)
into a single unified CLI interface.

Usage:
    notte workflow create <file>
    notte workflow run <file>
    notte workflow benchmark <file>
"""

from __future__ import annotations

from pathlib import Path

import typer

from notte_sdk.cli import workflow

# Main CLI app
app = typer.Typer(
    name="notte",
    help="Notte CLI - Manage workflows, sessions, agents, and more",
    add_completion=False,
    no_args_is_help=True,
)

# Add workflow subcommand
app.add_typer(workflow.workflow_app, name="workflow")

# Future subcommands can be added here:
# from notte_sdk.cli import session
# app.add_typer(session.session_app, name="session")
#
# from notte_sdk.cli import agent
# app.add_typer(agent.agent_app, name="agent")


def main(_file_path: Path | None = None) -> None:
    """
    Main CLI entry point.

    Args:
        _file_path: Optional path to workflow file. If None, will be auto-detected from sys.argv.
            Currently unused, kept for compatibility with workflow_cli().
    """
    # Run typer app directly - typer handles help, argument parsing, etc.
    app()


if __name__ == "__main__":
    main()
