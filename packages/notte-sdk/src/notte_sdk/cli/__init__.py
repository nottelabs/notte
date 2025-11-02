from __future__ import annotations

import importlib.util
import json
import os
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


def get_default_file_path() -> Path:
    """Get the default file path from sys.argv[0] if running from a workflow file."""
    if len(sys.argv) > 1 and sys.argv[1] in ["create", "update", "run"]:
        # Running as: python workflow_file.py create
        return Path(sys.argv[0]).resolve()
    # Default fallback - will raise error if not provided
    raise typer.BadParameter("File path is required when not running from a workflow file")


def find_workflow_function(module: Any) -> tuple[Any, str] | None:
    """
    Find the workflow function in a module.

    Args:
        module: The imported module.

    Returns:
        Tuple of (function, function_name) if found, None otherwise.
    """
    for name in dir(module):
        obj = getattr(module, name)
        if callable(obj) and is_workflow(obj):
            return obj, name
    return None


def load_workflow_file(file_path: Path) -> tuple[Any, str, Any]:
    """
    Load a workflow file and find the workflow function.

    Args:
        file_path: Path to the workflow Python file.

    Returns:
        Tuple of (module, function_name, function).

    Raises:
        ValueError: If no workflow function is found.
    """
    # Set __name__ to something other than "__main__" to prevent execution of if __name__ == "__main__" block
    import sys

    original_argv = sys.argv.copy()
    try:
        # Temporarily modify sys.argv to prevent the workflow from thinking it's being run directly
        # Save original to restore later
        spec = importlib.util.spec_from_file_location("workflow_module", file_path)
        if spec is None or spec.loader is None:
            raise ValueError(f"Could not load module from {file_path}")

        module = importlib.util.module_from_spec(spec)
        # Set __name__ to the module name (not "__main__") so if __name__ == "__main__" blocks don't execute
        module.__name__ = spec.name
        spec.loader.exec_module(module)

        result = find_workflow_function(module)
        if result is None:
            raise ValueError(
                f"No workflow function found in {file_path}. Make sure to decorate a function with @workflow."
            )

        func, func_name = result
        return module, func_name, func
    finally:
        # Restore original sys.argv
        sys.argv = original_argv


def get_api_key(api_key: str | None = None) -> str:
    """
    Get API key from argument or environment variable.

    Args:
        api_key: Optional API key from CLI argument.

    Returns:
        The API key.

    Raises:
        ValueError: If no API key is found.
    """
    if api_key:
        return api_key
    api_key = os.getenv("NOTTE_API_KEY")
    if not api_key:
        raise ValueError("NOTTE_API_KEY not found. Set it in environment or use --api-key flag.")
    return api_key


def prepare_workflow_file_for_upload(file_path: Path) -> tuple[Path, bool]:
    """
    Prepare a workflow file for upload by commenting out the __main__ block.

    Args:
        file_path: Path to the workflow file.

    Returns:
        Tuple of (temp_file_path, was_commented) where temp_file_path is the path to
        the temporary file with commented __main__ block, and was_commented indicates
        if the block was found and commented.
    """
    # Read current content
    content = file_path.read_text(encoding="utf-8")

    # Comment out __main__ block
    content, commented = comment_main_block(content)
    if commented:
        logger.debug("Commented out __main__ block for upload")

    # Write temporary file with .py extension (API requires .py files)
    temp_file = file_path.parent / f".{file_path.stem}_temp{file_path.suffix}"
    _ = temp_file.write_text(content, encoding="utf-8")

    return temp_file, commented


def restore_workflow_file(file_path: Path, was_commented: bool) -> None:
    """
    Restore the workflow file by uncommenting the __main__ block if needed.

    Args:
        file_path: Path to the workflow file.
        was_commented: Whether the __main__ block was commented out.
    """
    if was_commented:
        # Read content again
        content = file_path.read_text(encoding="utf-8")

        # Uncomment __main__ block
        content, _ = uncomment_main_block(content)

        # Write back to file
        _ = file_path.write_text(content, encoding="utf-8")


@app.command()
def create(
    file: Annotated[
        Path,
        typer.Argument(
            help="Path to the workflow Python file",
            default_factory=get_default_file_path,
        ),
    ],
    api_key: Annotated[
        str | None, typer.Option("--api-key", help="Notte API key (defaults to NOTTE_API_KEY environment variable")
    ] = None,
) -> None:
    """Create a new workflow."""
    try:
        api_key = get_api_key(api_key)
    except ValueError as e:
        logger.error(str(e))
        raise typer.Exit(1)

    logger.info(f"Creating workflow from {file}")

    # Load the workflow function
    _module, _func_name, func = load_workflow_file(file)

    # Get workflow metadata from decorator
    name = get_workflow_name(func)
    description = get_workflow_description(func)

    if not name:
        logger.error("Workflow name is required. Set it in the @workflow decorator.")
        raise typer.Exit(1)

    # Check if metadata already exists
    existing_metadata = WorkflowMetadata.from_file(file)
    if existing_metadata and existing_metadata.workflow_id:
        logger.error(
            f"Workflow already exists with ID: {existing_metadata.workflow_id}. Use 'update' command to update it."
        )
        raise typer.Exit(1)

    try:
        # Prepare file for upload (comment out __main__ block)
        temp_file, was_commented = prepare_workflow_file_for_upload(file)

        try:
            # Create client and workflow
            client = NotteClient(api_key=api_key)
            workflow_obj = client.Workflow(
                workflow_path=str(temp_file), name=name, description=description, _client=client
            )

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

            # Read current content
            content = file.read_text(encoding="utf-8")

            # Insert metadata block
            content = insert_metadata_block(content, metadata)

            # Write back to file
            _ = file.write_text(content, encoding="utf-8")

            # Restore __main__ block if it was commented
            restore_workflow_file(file, was_commented)

            logger.info(f"Metadata block added to {file}")
            logger.info(f"You can reference this workflow using: notte.Workflow('{workflow_obj.workflow_id}')")
        finally:
            # Clean up temp file
            if temp_file.exists():
                temp_file.unlink()
    except Exception as e:
        logger.error(f"Error: {e}")
        raise typer.Exit(1)


@app.command()
def update(
    file: Annotated[
        Path,
        typer.Argument(
            help="Path to the workflow Python file",
            default_factory=get_default_file_path,
        ),
    ],
    api_key: Annotated[
        str | None, typer.Option("--api-key", help="Notte API key (defaults to NOTTE_API_KEY environment variable")
    ] = None,
    restricted: Annotated[
        bool, typer.Option("--restricted/--no-restricted", help="Run workflow in restricted mode")
    ] = True,
) -> None:
    """Update an existing workflow."""
    try:
        api_key = get_api_key(api_key)
    except ValueError as e:
        logger.error(str(e))
        raise typer.Exit(1)

    logger.info(f"Updating workflow from {file}")

    # Read metadata
    metadata = WorkflowMetadata.from_file(file)
    if not metadata or not metadata.workflow_id:
        logger.error("No workflow metadata found. Run 'create' command first to create the workflow.")
        raise typer.Exit(1)

    # Prepare file for upload (comment out __main__ block)
    temp_file, was_commented = prepare_workflow_file_for_upload(file)

    try:
        # Update workflow
        client = NotteClient(api_key=api_key)
        workflow_obj = client.Workflow(workflow_id=metadata.workflow_id, _client=client)
        workflow_obj.update(workflow_path=str(temp_file), restricted=restricted)

        logger.info(f"Workflow {metadata.workflow_id} updated successfully")

        # Update metadata
        metadata.last_update_date = workflow_obj.response.updated_at.isoformat()

        # Read content again (may have been modified)
        content = file.read_text(encoding="utf-8")

        # Insert metadata block
        content = insert_metadata_block(content, metadata)

        # Write back to file
        _ = file.write_text(content, encoding="utf-8")

        # Restore __main__ block if it was commented
        restore_workflow_file(file, was_commented)

        logger.info(f"Metadata updated in {file}")
    except Exception as e:
        logger.error(f"Error: {e}")
        raise typer.Exit(1)
    finally:
        # Clean up temp file
        if temp_file.exists():
            temp_file.unlink()


@app.command()
def run(
    file: Annotated[
        Path,
        typer.Argument(
            help="Path to the workflow Python file",
            default_factory=get_default_file_path,
        ),
    ],
    api_key: Annotated[
        str | None, typer.Option("--api-key", help="Notte API key (defaults to NOTTE_API_KEY environment variable")
    ] = None,
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
        # For local runs, just execute the file
        # This mimics: uv run python workflow_code.py
        import subprocess

        result = subprocess.run([sys.executable, str(file)], check=False)
        raise typer.Exit(result.returncode)
    else:
        try:
            api_key = get_api_key(api_key)
        except ValueError as e:
            logger.error(str(e))
            raise typer.Exit(1)

        logger.info(f"Running workflow on cloud from {file}")

        # Read metadata
        metadata = WorkflowMetadata.from_file(file)
        if not metadata or not metadata.workflow_id:
            logger.error("No workflow metadata found. Run 'create' command first to create the workflow.")
            raise typer.Exit(1)

        # Load variables if provided
        variables_dict: dict[str, Any] = {}
        if variables:
            if not variables.exists():
                logger.error(f"Variables file not found: {variables}")
                raise typer.Exit(1)
            variables_dict = json.loads(variables.read_text(encoding="utf-8"))

        try:
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
        except Exception as e:
            logger.error(f"Error: {e}")
            raise typer.Exit(1)


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
