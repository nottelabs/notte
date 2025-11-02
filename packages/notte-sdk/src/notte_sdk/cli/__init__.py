from __future__ import annotations

import contextlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from notte_core.common.logging import logger

from notte_sdk.cli.metadata import (
    WorkflowMetadata,
    comment_main_block,
    get_git_author,
    insert_metadata_block,
    uncomment_main_block,
)
from notte_sdk.client import NotteClient
from notte_sdk.decorators import get_workflow_description, get_workflow_name, is_workflow

app = typer.Typer(
    name="notte-workflow",
    help="Notte Workflow CLI - Manage workflow lifecycle from your workflow files",
    add_completion=False,
    no_args_is_help=True,
)


# Common argument definitions
def get_default_file_path() -> Path:
    """Get the default file path from sys.argv[0] if running from a workflow file."""
    if len(sys.argv) > 1 and sys.argv[1] in ["create", "update", "run"]:
        return Path(sys.argv[0]).resolve()
    raise typer.BadParameter("File path is required when not running from a workflow file")


FILE_ARG = Annotated[
    Path,
    typer.Argument(
        help="Path to the workflow Python file",
        default_factory=get_default_file_path,
    ),
]

API_KEY_ARG = Annotated[
    str | None,
    typer.Option(
        "--api-key",
        help="Notte API key (defaults to NOTTE_API_KEY environment variable)",
        envvar="NOTTE_API_KEY",
    ),
]


def find_workflow_function(module: Any) -> tuple[Any, str] | None:
    """Find the workflow function in a module."""
    for name in dir(module):
        obj = getattr(module, name)
        if callable(obj) and is_workflow(obj):
            return obj, name
    return None


def load_workflow_file(file_path: Path) -> tuple[Any, str, Any]:
    """
    Load a workflow file and find the workflow function.

    Sets __name__ to prevent execution of if __name__ == "__main__" blocks.
    """
    spec = importlib.util.spec_from_file_location("workflow_module", file_path)
    if spec is None or spec.loader is None:
        raise typer.BadParameter(f"Could not load module from {file_path}")

    module = importlib.util.module_from_spec(spec)
    # Set __name__ to module name (not "__main__") to prevent __main__ block execution
    module.__name__ = spec.name
    spec.loader.exec_module(module)

    result = find_workflow_function(module)
    if result is None:
        raise typer.BadParameter(
            f"No workflow function found in {file_path}. Make sure to decorate a function with @workflow."
        )

    func, func_name = result
    return module, func_name, func


@contextlib.contextmanager
def workflow_file_for_upload(file_path: Path):
    """
    Context manager for preparing workflow file for upload.

    Comments out __main__ block, yields temp file, then restores original.
    """
    content = file_path.read_text(encoding="utf-8")
    content, was_commented = comment_main_block(content)
    if was_commented:
        logger.debug("Commented out __main__ block for upload")

    temp_file = file_path.parent / f".{file_path.stem}_temp{file_path.suffix}"
    _ = temp_file.write_text(content, encoding="utf-8")

    try:
        yield temp_file
    finally:
        # Clean up temp file
        if temp_file.exists():
            temp_file.unlink()
        # Restore __main__ block if it was commented
        if was_commented:
            content = file_path.read_text(encoding="utf-8")
            content, _ = uncomment_main_block(content)
            _ = file_path.write_text(content, encoding="utf-8")


def get_workflow_metadata(file_path: Path, require_id: bool = False) -> WorkflowMetadata:
    """Get workflow metadata from file, raising typer errors if invalid."""
    metadata = WorkflowMetadata.from_file(file_path)
    if not metadata:
        raise typer.BadParameter("No workflow metadata found. Run 'create' command first.")
    if require_id:
        if not metadata.workflow_id:
            raise typer.BadParameter("No workflow ID found. Run 'create' command first.")
        # Type narrowing: at this point workflow_id is guaranteed to be str
        assert metadata.workflow_id is not None
    return metadata


def update_metadata_in_file(file_path: Path, metadata: WorkflowMetadata) -> None:
    """Update metadata block in workflow file."""
    content = file_path.read_text(encoding="utf-8")
    content = insert_metadata_block(content, metadata)
    _ = file_path.write_text(content, encoding="utf-8")


@app.command()
def create(
    file: FILE_ARG,
    api_key: API_KEY_ARG = None,
) -> None:
    """Create a new workflow."""
    if not api_key:
        raise typer.BadParameter("NOTTE_API_KEY not found. Set it in environment or use --api-key flag.")

    logger.info(f"Creating workflow from {file}")

    # Load the workflow function
    _module, _func_name, func = load_workflow_file(file)

    # Get workflow metadata from decorator
    name = get_workflow_name(func)
    description = get_workflow_description(func)

    if not name:
        raise typer.BadParameter("Workflow name is required. Set it in the @workflow decorator.")

    # Check if metadata already exists
    existing_metadata = WorkflowMetadata.from_file(file)
    if existing_metadata and existing_metadata.workflow_id:
        raise typer.BadParameter(
            f"Workflow already exists with ID: {existing_metadata.workflow_id}. Use 'update' command to update it."
        )

    with workflow_file_for_upload(file) as temp_file:
        # Create client and workflow
        client = NotteClient(api_key=api_key)
        workflow_obj = client.Workflow(workflow_path=str(temp_file), name=name, description=description, _client=client)

        logger.info(f"Workflow created with ID: {workflow_obj.workflow_id}")

        # Create metadata and insert into file
        metadata = WorkflowMetadata(
            workflow_id=workflow_obj.workflow_id,
            name=name,
            description=description,
            author=get_git_author(file),
            creation_date=workflow_obj.response.created_at.isoformat(),
            last_update_date=workflow_obj.response.updated_at.isoformat(),
        )

        update_metadata_in_file(file, metadata)

        logger.info(f"Metadata block added to {file}")
        logger.info(f"You can reference this workflow using: notte.Workflow('{workflow_obj.workflow_id}')")


@app.command()
def update(
    file: FILE_ARG,
    api_key: API_KEY_ARG = None,
    restricted: Annotated[
        bool, typer.Option("--restricted/--no-restricted", help="Run workflow in restricted mode")
    ] = True,
) -> None:
    """Update an existing workflow."""
    if not api_key:
        raise typer.BadParameter("NOTTE_API_KEY not found. Set it in environment or use --api-key flag.")

    logger.info(f"Updating workflow from {file}")

    # Read metadata
    metadata = get_workflow_metadata(file, require_id=True)
    # Type narrowing: workflow_id is guaranteed to be str when require_id=True
    assert metadata.workflow_id is not None

    with workflow_file_for_upload(file) as temp_file:
        # Update workflow
        client = NotteClient(api_key=api_key)
        workflow_obj = client.Workflow(workflow_id=metadata.workflow_id, _client=client)
        workflow_obj.update(workflow_path=str(temp_file), restricted=restricted)

        logger.info(f"Workflow {metadata.workflow_id} updated successfully")

        # Update metadata
        metadata.last_update_date = workflow_obj.response.updated_at.isoformat()
        update_metadata_in_file(file, metadata)

        logger.info(f"Metadata updated in {file}")


@app.command()
def run(
    file: FILE_ARG,
    api_key: API_KEY_ARG = None,
    local: Annotated[bool, typer.Option("--local", help="Run workflow locally instead of on cloud")] = False,
    variables: Annotated[
        Path | None, typer.Option("--variables", help="JSON file containing workflow variables")
    ] = None,
    timeout: Annotated[int | None, typer.Option("--timeout", help="Timeout in seconds for cloud runs")] = None,
    stream: Annotated[
        bool, typer.Option("--stream/--no-stream", help="Enable/disable streaming logs for cloud runs")
    ] = True,
    raise_on_failure: Annotated[
        bool, typer.Option("--raise-on-failure/--no-raise-on-failure", help="Raise exception on workflow failure")
    ] = True,
) -> None:
    """Run a workflow."""
    if local:
        logger.info(f"Running workflow locally from {file}")
        import subprocess

        result = subprocess.run([sys.executable, str(file)], check=False)
        raise typer.Exit(result.returncode)

    if not api_key:
        raise typer.BadParameter("NOTTE_API_KEY not found. Set it in environment or use --api-key flag.")

    logger.info(f"Running workflow on cloud from {file}")

    # Read metadata
    metadata = get_workflow_metadata(file, require_id=True)
    # Type narrowing: workflow_id is guaranteed to be str when require_id=True
    assert metadata.workflow_id is not None

    # Load variables if provided
    variables_dict: dict[str, Any] = {}
    if variables:
        if not variables.exists():
            raise typer.BadParameter(f"Variables file not found: {variables}")
        variables_dict = json.loads(variables.read_text(encoding="utf-8"))

    # Run workflow
    client = NotteClient(api_key=api_key)
    workflow_obj = client.Workflow(workflow_id=metadata.workflow_id, _client=client)
    result = workflow_obj.run(
        timeout=timeout,
        stream=stream,
        raise_on_failure=raise_on_failure,
        **variables_dict,
    )

    logger.info(f"Workflow completed with status: {result.status}")
    logger.info(f"Result: {result.result}")


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
