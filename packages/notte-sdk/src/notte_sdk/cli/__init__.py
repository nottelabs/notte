from __future__ import annotations

import contextlib
import importlib.util
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Annotated, Any, Callable

import typer
from notte_core.common.logging import logger
from tqdm import tqdm

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
    if len(sys.argv) > 1 and sys.argv[1] in ["create", "update", "run", "benchmark"]:
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

SERVER_URL_ARG = Annotated[
    str | None,
    typer.Option(
        "--server-url",
        help="Notte API server URL (defaults to NOTTE_API_URL environment variable)",
        envvar="NOTTE_API_URL",
    ),
]


def find_workflow_function(module: Any) -> tuple[Any, str] | None:
    """Find the workflow function in a module.

    First tries to find a function with @workflow decorator.
    If not found, tries to find a function named 'run' or the only function in the module.
    """
    # First, try to find a function with @workflow decorator
    for name in dir(module):
        obj = getattr(module, name)
        if callable(obj) and is_workflow(obj):
            return obj, name

    # If no decorated function found, try to find 'run' function
    if hasattr(module, "run"):
        obj = getattr(module, "run")
        if callable(obj) and not obj.__name__.startswith("_"):  # Skip private functions
            return obj, "run"

    # Last resort: if there's only one callable function, use it
    callable_functions: list[tuple[Callable[..., Any], str]] = []
    for name in dir(module):
        obj = getattr(module, name)
        if (
            callable(obj)
            and not name.startswith("_")
            and not isinstance(obj, type)  # Skip classes
            and not isinstance(obj, type(__builtins__))  # Skip builtins
        ):
            # Skip common non-workflow functions
            if name not in ["main", "app", "cli"]:
                callable_functions.append((obj, name))

    if len(callable_functions) == 1:
        return callable_functions[0]

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
            f"No workflow function found in {file_path}. "
            + "Either decorate a function with @workflow, name it 'run', or ensure there's only one function in the file."
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
    server_url: SERVER_URL_ARG = None,
) -> None:
    """Create a new workflow."""
    if not api_key:
        raise typer.BadParameter("NOTTE_API_KEY not found. Set it in environment or use --api-key flag.")

    logger.info(f"Creating workflow from {file}")

    # Load the workflow function
    _module, _func_name, func = load_workflow_file(file)

    # Get workflow metadata from decorator (if present)
    name = get_workflow_name(func)
    description = get_workflow_description(func)

    # If no decorator found, prompt interactively
    if not name:
        # Suggest a default name based on file name
        default_name = file.stem.replace("_", " ").title()

        logger.info("No @workflow decorator found. Please provide workflow metadata:")
        name = typer.prompt("Workflow name", default=default_name)
        description = typer.prompt("Workflow description (optional)", default="", show_default=False)
        if not description.strip():
            description = None

    # Check if metadata already exists
    existing_metadata = WorkflowMetadata.from_file(file)
    if existing_metadata and existing_metadata.workflow_id:
        raise typer.BadParameter(
            f"Workflow already exists with ID: {existing_metadata.workflow_id}. Use 'update' command to update it."
        )

    with workflow_file_for_upload(file) as temp_file:
        # Create client and workflow
        client = NotteClient(api_key=api_key, server_url=server_url)
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
    server_url: SERVER_URL_ARG = None,
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
        client = NotteClient(api_key=api_key, server_url=server_url)
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
    server_url: SERVER_URL_ARG = None,
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
    client = NotteClient(api_key=api_key, server_url=server_url)
    workflow_obj = client.Workflow(workflow_id=metadata.workflow_id, _client=client)
    result = workflow_obj.run(
        timeout=timeout,
        stream=stream,
        raise_on_failure=raise_on_failure,
        **variables_dict,
    )

    logger.info(f"Workflow completed with status: {result.status}")
    logger.info(f"Result: {result.result}")


@app.command()
def benchmark(
    file: FILE_ARG,
    api_key: API_KEY_ARG = None,
    server_url: SERVER_URL_ARG = None,
    local: Annotated[bool, typer.Option("--local", help="Run workflow locally instead of on cloud")] = False,
    iterations: Annotated[int, typer.Option("--iterations", help="Maximum number of iterations to run")] = 10,
    timeout: Annotated[int, typer.Option("--timeout", help="Timeout in minutes for the entire benchmark")] = 20,
    parallelism: Annotated[int, typer.Option("--parallelism", help="Number of parallel runs (default: 1)")] = 1,
    variables: Annotated[
        Path | None, typer.Option("--variables", help="JSON file containing workflow variables")
    ] = None,
) -> None:
    """Run a benchmark test with multiple iterations of the workflow."""
    timeout_seconds = timeout * 60  # Convert minutes to seconds

    # Interactive prompts if running without flags
    # Check if any benchmark-specific flags were provided
    benchmark_flags = ["--local", "--iterations", "--timeout", "--variables", "--parallelism"]
    has_flags = any(flag in sys.argv for flag in benchmark_flags)

    if not has_flags:
        logger.info("Running benchmark interactively. Press Enter to use defaults.")
        logger.info("")

        # Prompt for local vs cloud
        while True:
            local_input = (
                typer.prompt(
                    "Run locally or on cloud? [local/cloud]",
                    default="cloud",
                )
                .strip()
                .lower()
            )
            if local_input in ["local", "cloud"]:
                local = local_input == "local"
                break
            logger.error("Please enter 'local' or 'cloud'")

        # Prompt for iterations
        iterations = typer.prompt("Number of iterations", default=10, type=int)

        # Prompt for timeout
        timeout = typer.prompt("Timeout in minutes", default=20, type=int)

        # Prompt for parallelism
        parallelism = typer.prompt("Parallelism level (number of parallel runs)", default=1, type=int)
        if parallelism < 1:
            parallelism = 1
        if parallelism > iterations:
            parallelism = iterations
            logger.warning(f"Parallelism reduced to {iterations} (cannot exceed number of iterations)")

        # Prompt for variables file (optional)
        variables_input = typer.prompt(
            "Variables file path (optional, press Enter to skip)",
            default="",
            show_default=False,
        )
        if variables_input.strip():
            variables = Path(variables_input.strip())
            if not variables.exists():
                raise typer.BadParameter(f"Variables file not found: {variables}")
        else:
            variables = None

        logger.info("")

    # Validate parallelism
    if parallelism < 1:
        parallelism = 1
    if parallelism > iterations:
        parallelism = iterations
        logger.warning(f"Parallelism reduced to {iterations} (cannot exceed number of iterations)")

    if local:
        logger.info(
            f"Running benchmark locally from {file} ({iterations} iterations, {timeout} min timeout, parallelism={parallelism})"
        )
    else:
        if not api_key:
            raise typer.BadParameter("NOTTE_API_KEY not found. Set it in environment or use --api-key flag.")
        logger.info(
            f"Running benchmark on cloud from {file} ({iterations} iterations, {timeout} min timeout, parallelism={parallelism})"
        )

    # Read metadata for cloud runs
    metadata: WorkflowMetadata | None = None
    workflow_obj: Any | None = None
    if not local:
        metadata = get_workflow_metadata(file, require_id=True)
        assert metadata.workflow_id is not None
        client = NotteClient(api_key=api_key, server_url=server_url)
        workflow_obj = client.Workflow(workflow_id=metadata.workflow_id, _client=client)

    # Load variables if provided
    variables_dict: dict[str, Any] = {}
    if variables:
        if not variables.exists():
            raise typer.BadParameter(f"Variables file not found: {variables}")
        variables_dict = json.loads(variables.read_text(encoding="utf-8"))

    # Helper function to run a single iteration
    def run_iteration(iteration_num: int) -> dict[str, Any]:
        """Run a single benchmark iteration."""
        iteration_start = time.time()
        workflow_id: str | None = None
        try:
            if local:
                # Run locally
                import subprocess

                result = subprocess.run(
                    [sys.executable, str(file)],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                iteration_end = time.time()
                execution_time = iteration_end - iteration_start
                success = result.returncode == 0
                run_id = f"local-{iteration_num}"
                status = "closed" if success else "failed"
                workflow_id = metadata.workflow_id if metadata else None
            else:
                # Run on cloud
                assert workflow_obj is not None
                assert metadata is not None
                result = workflow_obj.run(
                    timeout=None,  # Use default timeout per run
                    stream=False,
                    raise_on_failure=False,  # Don't raise for benchmark
                    **variables_dict,
                )
                iteration_end = time.time()
                execution_time = iteration_end - iteration_start
                success = result.status == "closed"
                run_id = result.workflow_run_id
                workflow_id = result.workflow_id  # Get workflow_id from response
                status = result.status

            return {
                "iteration": iteration_num,
                "success": success,
                "execution_time": execution_time,
                "run_id": run_id,
                "status": status,
                "workflow_id": workflow_id,
            }
        except Exception as e:
            iteration_end = time.time()
            execution_time = iteration_end - iteration_start
            logger.error(f"\nIteration {iteration_num} failed with exception: {e}")
            return {
                "iteration": iteration_num,
                "success": False,
                "execution_time": execution_time,
                "run_id": f"error-{iteration_num}",
                "status": "failed",
                "workflow_id": metadata.workflow_id if metadata else None,
            }

    # Benchmark results
    results: list[dict[str, Any]] = []
    start_time = time.time()

    # Create progress bar
    pbar = tqdm(
        total=iterations,
        desc="Benchmark progress",
        unit="run",
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
    )

    try:
        if parallelism == 1:
            # Sequential execution (original behavior)
            for i in range(iterations):
                # Check if we've exceeded the timeout
                elapsed = time.time() - start_time
                if elapsed >= timeout_seconds:
                    pbar.close()
                    logger.info(f"\nTimeout reached ({timeout} min). Stopping benchmark after {i} iterations.")
                    break

                # Update progress bar description with current iteration
                pbar.set_description(f"Running iteration {i + 1}/{iterations}")
                result = run_iteration(i + 1)
                results.append(result)

                # Update progress bar with result
                status_icon = "✅" if result["success"] else "❌"
                pbar.set_postfix_str(f"{status_icon} {result['execution_time']:.2f}s")
                _ = pbar.update(1)
        else:
            # Parallel execution
            with ThreadPoolExecutor(max_workers=parallelism) as executor:
                # Submit all tasks
                future_to_iteration = {executor.submit(run_iteration, i + 1): i + 1 for i in range(iterations)}

                # Process completed futures as they finish
                for future in as_completed(future_to_iteration):
                    # Check if we've exceeded the timeout
                    elapsed = time.time() - start_time
                    if elapsed >= timeout_seconds:
                        pbar.close()
                        logger.info(f"\nTimeout reached ({timeout} min). Cancelling remaining tasks...")
                        # Cancel remaining futures
                        for f in future_to_iteration:
                            _ = f.cancel()
                        break

                    try:
                        result = future.result()
                        results.append(result)

                        # Update progress bar with result
                        status_icon = "✅" if result["success"] else "❌"
                        pbar.set_postfix_str(f"{status_icon} {result['execution_time']:.2f}s")
                        _ = pbar.update(1)
                    except Exception as e:
                        iteration_num = future_to_iteration[future]
                        logger.error(f"\nIteration {iteration_num} failed with exception: {e}")
                        results.append(
                            {
                                "iteration": iteration_num,
                                "success": False,
                                "execution_time": 0.0,
                                "run_id": f"error-{iteration_num}",
                                "status": "failed",
                                "workflow_id": metadata.workflow_id if metadata else None,
                            }
                        )
                        _ = pbar.update(1)

            # Sort results by iteration number for consistent display
            results.sort(key=lambda x: x["iteration"])

    finally:
        pbar.close()
        logger.info("")  # New line after progress bar

    # Calculate summary statistics
    total_runs = len(results)
    successful_runs = sum(1 for r in results if r["success"])
    failed_runs = total_runs - successful_runs
    success_rate = (successful_runs / total_runs * 100) if total_runs > 0 else 0.0

    # Calculate average execution time for successful runs, or failed runs if all failed
    if successful_runs > 0:
        avg_execution_time = sum(r["execution_time"] for r in results if r["success"]) / successful_runs
    elif failed_runs > 0:
        avg_execution_time = sum(r["execution_time"] for r in results if not r["success"]) / failed_runs
    else:
        avg_execution_time = 0.0

    # Use consistent width for all separators
    # Table columns: Status (8) + Time (12) + Run ID (40) + Console URL (80) + 3 spaces = 143 chars
    separator_width = 143
    separator_double = "=" * separator_width
    separator_single = "-" * separator_width

    # Display summary
    logger.info("")
    logger.info(separator_double)
    logger.info("BENCHMARK SUMMARY")
    logger.info(separator_double)
    logger.info(f"Total runs: {total_runs}")
    logger.info(f"Successful: {successful_runs}")
    logger.info(f"Failed: {failed_runs}")
    logger.info(f"Success rate: {success_rate:.1f}%")
    logger.info(f"Average execution time: {avg_execution_time:.2f}s")
    logger.info(f"Total benchmark time: {time.time() - start_time:.2f}s")
    logger.info(separator_double)

    # Display results table
    logger.info("")
    logger.info("Detailed Results:")
    logger.info(separator_single)

    # Table header
    header = f"{'Status':<8} {'Time':<12} {'Run ID':<40} {'Console URL':<80}"
    logger.info(header)
    logger.info(separator_single)

    for r in results:
        status_icon = "✅" if r["success"] else "❌"
        execution_time_str = f"{r['execution_time']:.2f}s"
        run_id_str = r["run_id"][:38]  # Truncate if too long

        # Build console URL using workflow_id and run_id from response
        if r["workflow_id"] and not local:
            console_url = f"https://console.notte.cc/logs/workflows/{r['workflow_id']}/runs/{r['run_id']}"
        else:
            console_url = "N/A (local run)"

        row = f"{status_icon:<8} {execution_time_str:<12} {run_id_str:<40} {console_url:<80}"
        logger.info(row)

    logger.info(separator_single)

    # Exit with error code if all runs failed
    if failed_runs == total_runs and total_runs > 0:
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
