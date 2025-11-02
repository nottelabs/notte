"""
Helper function for workflow files to enable CLI commands.

Call this in your `if __name__ == "__main__"` block. If CLI arguments are detected,
it handles them and exits. Otherwise, it returns immediately and your code continues normally.

Example:
```python
from notte_sdk import NotteClient, workflow, workflow_cli

notte = NotteClient()

@workflow(name="My Workflow")
def run():
    ...

if __name__ == "__main__":
    workflow_cli()  # Handles CLI or does nothing
    # Your custom code continues here if no CLI args
    run()
```

This allows you to run commands like:
- python workflow_file.py create
- python workflow_file.py run --local
- python workflow_file.py update
- python workflow_file.py run --variables variables.json
- python workflow_file.py benchmark --iterations 10 --timeout 20
- python workflow_file.py benchmark --local --iterations 5

Note: The @workflow decorator is optional. If you don't use it, the CLI will
prompt for workflow name and description during creation.
"""

from __future__ import annotations

import sys

from notte_sdk.cli import main


def workflow_cli() -> None:
    """
    CLI entry point for workflow files.

    Call this anywhere in your `if __name__ == "__main__"` block.
    If CLI arguments are detected, it handles them and exits.
    Otherwise, it returns immediately and your code continues normally.
    """
    # Only handle CLI if args are present
    if len(sys.argv) > 1:
        first_arg = sys.argv[1]
        if first_arg in ["create", "update", "run", "benchmark", "--help", "-h"]:
            # Handle CLI and exit
            # Note: file_path is auto-detected from sys.argv by typer, so we don't need to pass it
            main()
            sys.exit(0)

    # No CLI args - return immediately, let normal execution continue
    return
