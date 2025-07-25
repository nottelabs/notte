from __future__ import annotations

import argparse
import asyncio
import contextlib
import functools
import io
import logging
import sys
import time
import tomllib
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TextIO

import cloudpickle  # type: ignore[reportMissingTypeStubs]
import pebble
from loguru import logger as loguru_logger
from notte_core.utils.webp_replay import ScreenshotReplay
from pydantic import BaseModel
from typing_extensions import Self

from notte_eval.agent_handlers import fetch_handler
from notte_eval.data.load_data import (
    BenchmarkTask,
)
from notte_eval.evaluators import EVALUATORS_DICT, fetch_evaluator
from notte_eval.evaluators.evaluator import Evaluator
from notte_eval.task_types import (
    AgentBenchmark,
    AgentOut,
    AgentParams,
    LoggingSink,
    TaskResult,
)


class TaskSet(BaseModel):
    name: str
    start: int | None = None
    end: int | None = None


class RunParameters(BaseModel):
    n_jobs: int
    tries_per_task: int
    task_set: TaskSet
    max_task_duration_in_s: float = 5 * 60
    evaluator: Evaluator | None = None
    experiment_path: Path | str = ""
    capture_logging: bool = True


class InRunParameters(BaseModel):
    class Config:
        frozen: bool = True

    run_id: int
    evaluator: Evaluator | None = None
    experiment_path: Path | str = ""
    capture_logging: bool = True


TaskSuccessResult = tuple[BenchmarkTask, AgentOut, TaskResult]


@dataclass
class TaskErrorResult:
    task: BenchmarkTask
    run_params: InRunParameters
    logs: dict[str, str]
    experiment_path: str | Path
    exception: Exception | None = None
    traceback_str: str | None = None
    logged: bool = False

    def log(self) -> Self:
        if self.logged:
            return self

        task_res = TaskResult(
            success=False,
            run_id=self.run_params.run_id,
            eval=None,
            duration_in_s=-1,
            agent_answer=f"Task failed {'due to ' + str(self.exception) if self.exception is not None else ''} {self.traceback_str}",
            task=self.task,
            steps=[],
            logs=self.logs,
            screenshots=ScreenshotReplay.from_base64([]),
        )

        save_task(self.experiment_path, task_res)

        self.logged = True
        return self


class BenchmarkExecutionResult:
    def __init__(self, success: bool, data: TaskSuccessResult[Any] | TaskErrorResult):
        self.success: bool = success
        self.data: TaskSuccessResult[Any] | TaskErrorResult = data

    @classmethod
    def successful(cls, data: TaskSuccessResult[Any]) -> Self:
        return cls(True, data)

    @classmethod
    def failure(cls, error_result: TaskErrorResult) -> Self:
        return cls(False, error_result)


def setup_logging(log_stream: io.StringIO) -> None:
    """
    Configure logging to capture all logs regardless of source package.
    Forces all loggers to propagate to root and captures everything.
    """
    # First, reset all existing loggers to propagate to root
    logging.getLogger().setLevel(logging.INFO)
    for name in logging.root.manager.loggerDict:
        logger = logging.getLogger(name)
        logger.handlers = []  # Remove any direct handlers
        logger.propagate = True  # Ensure propagation to root
        logger.setLevel(logging.INFO)

    # Create and configure the stream handler
    stream_handler = logging.StreamHandler(log_stream)
    stream_handler.setLevel(logging.INFO)

    # Clear any existing handlers from root logger
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add our handler to root logger
    root_logger.addHandler(stream_handler)


def sync_wrapper(async_func: Callable[..., Any], *args: tuple[Any, ...], **kwargs: dict[str, Any]):
    """Wraps an async function to be called synchronously."""
    try:
        return asyncio.run(async_func(*args, **kwargs))  # Python 3.7+
    except RuntimeError as e:
        if "There is no current event loop" in str(e):
            # Create a new event loop if none exists.  This can happen
            # if this wrapper is called in a process that doesn't have one.
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(async_func(*args, **kwargs))
        else:
            raise


async def run_agent(
    agent_bench: AgentBenchmark[AgentParams, AgentOut],
    task: BenchmarkTask,
    inrun_params: InRunParameters,
) -> bytes | TaskErrorResult:
    log_capture = io.StringIO()
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()

    sink = LoggingSink()

    if inrun_params.capture_logging:
        loguru_logger.remove()
        _ = loguru_logger.add(sink, level="DEBUG")  # Redirect loguru logs

        setup_logging(log_capture)
    else:
        stdout_capture = sys.stdout
        stderr_capture = sys.stderr

    def get_logs() -> dict[str, str]:
        if not inrun_params.capture_logging:
            return {}

        assert isinstance(stderr_capture, io.StringIO) and isinstance(stdout_capture, io.StringIO)
        logs: dict[str, str] = {}
        logs["stdout"] = stdout_capture.getvalue()
        logs["stderr"] = stderr_capture.getvalue()
        logs["logging"] = log_capture.getvalue()
        logs["loguru"] = "\n".join(sink.messages)
        return logs

    try:
        with (
            contextlib.redirect_stdout(stdout_capture),
            contextlib.redirect_stderr(stderr_capture),
        ):
            run = await agent_bench.run_agent(task)
            out = await agent_bench.process_output(task, run)

            out.run_id = inrun_params.run_id

            if inrun_params.evaluator is not None:
                out.eval = await inrun_params.evaluator.eval(
                    answer=out.agent_answer,
                    task=task.question,
                    expected_answer=task.answer if task.answer is not None else "No expected result provided.",
                    screenshots=out.screenshots.to_bytes(),
                )

        if inrun_params.capture_logging:
            out.logs = get_logs()

        save_task(inrun_params.experiment_path, out)
        return cloudpickle.dumps((task, run, out))  # type: ignore[reportUnknownMemberType]

    except Exception as e:
        logging.error(f"{e}: {traceback.format_exc()}")

        return TaskErrorResult(
            task,
            inrun_params,
            get_logs(),
            inrun_params.experiment_path,
            exception=e,
            traceback_str=traceback.format_exc(),
        ).log()


def compute_tasks(
    agent_bench: AgentBenchmark[AgentParams, AgentOut], run_parameters: RunParameters
) -> list[BenchmarkExecutionResult]:
    try:
        task_class = BenchmarkTask.registry[run_parameters.task_set.name]
    except KeyError:
        raise ValueError(f"Invalid task set {run_parameters.task_set}, available: {BenchmarkTask.registry.keys()}")

    tasks = task_class.read_tasks()
    task_slice = slice(run_parameters.task_set.start, run_parameters.task_set.end)
    tasks = tasks[task_slice]

    futures: list[tuple[BenchmarkTask, InRunParameters, pebble.ProcessFuture]] = []
    gathered_outputs: list[bytes | TaskErrorResult] = []

    with pebble.ProcessPool(max_workers=run_parameters.n_jobs, max_tasks=1) as pool:
        for task in tasks:
            for run_id in range(run_parameters.tries_per_task):
                run_params = InRunParameters(
                    run_id=run_id,
                    evaluator=run_parameters.evaluator,
                    experiment_path=run_parameters.experiment_path,
                    capture_logging=run_parameters.capture_logging,
                )

                wrapped_task = functools.partial(
                    sync_wrapper,
                    run_agent,
                    agent_bench,  # type: ignore
                    task,  # type: ignore
                    run_params,  # type: ignore
                )
                future = pool.schedule(wrapped_task, timeout=run_parameters.max_task_duration_in_s)  # type: ignore[reportUnknownMemberType]
                futures.append((task, run_params, future))

        try:
            for task, run_params, future in futures:
                try:
                    result = future.result()  # type: ignore
                    assert isinstance(result, (bytes, TaskErrorResult))
                    gathered_outputs.append(result)

                # add timeout errors
                except Exception as e:
                    gathered_outputs.append(
                        TaskErrorResult(
                            task,
                            run_params,
                            {},
                            run_params.experiment_path,
                            exception=e,
                            traceback_str=traceback.format_exc(),
                        ).log()
                    )

        except KeyboardInterrupt:
            pool.stop()
            pool.join()
        finally:
            pool.stop()
            pool.join()

    final_outs: list[BenchmarkExecutionResult] = []
    for out in gathered_outputs:
        if isinstance(out, bytes):
            try:
                task_outputs: TaskSuccessResult = cloudpickle.loads(out)  # type: ignore
                final_outs.append(BenchmarkExecutionResult.successful(task_outputs))  # type: ignore
            except Exception:
                raise ValueError(
                    f"Could not read bytes from task return, this should not happen: {traceback.format_exc()}"
                )
        else:
            final_outs.append(BenchmarkExecutionResult.failure(out))

    return final_outs


def save_task(root_path: str | Path, task_res: TaskResult):
    if not isinstance(root_path, Path):
        path = Path(root_path)
    else:
        path = root_path

    path = path / f"{task_res.task_website}_{task_res.task_id}" / str(task_res.run_id)

    path.mkdir(parents=True, exist_ok=True)

    with open(path / "results.json", "w") as f:
        _ = f.write(task_res.model_dump_json(indent=2))

    with open(path / "results_no_screenshot.json", "w") as f:
        _ = f.write(task_res.model_dump_json(indent=2, exclude={"screenshots"}))

    with open(path / "summary.webp", "wb") as f:
        _ = f.write(task_res.screenshots.build_webp(start_text=task_res.task.question))


def load_data(input_stream: TextIO | None = None) -> dict[str, Any]:
    """
    Loads data from the given input stream (stdin by default).
    Returns the data as a string.
    """
    stream: TextIO
    if input_stream is None:
        stream = sys.stdin
    else:
        stream = input_stream

    data = stream.read()  # Read all data from the stream
    return tomllib.loads(data)


def run_tasks(config: dict[str, Any], dir: Path | str = ".") -> Path:
    RUN_PARAMS_KEY = "RunParameters"
    if RUN_PARAMS_KEY not in config:
        raise ValueError("Need to configure run with RunParameters table")

    run_params_dict = config[RUN_PARAMS_KEY]
    evaluator = run_params_dict["evaluator"]

    if evaluator == "None":
        run_params_dict["evaluator"] = None
    elif evaluator not in EVALUATORS_DICT:
        raise ValueError(f"No evaluator found for {evaluator}")
    else:
        run_params_dict["evaluator"] = fetch_evaluator(evaluator)()

    run_params = RunParameters.model_validate(run_params_dict)

    del config[RUN_PARAMS_KEY]

    if len(config) > 1:
        raise ValueError("Table should only have params for a single Agent")

    benchmark_handler_key = next(iter(config.keys()))
    bench_params = config[benchmark_handler_key]
    input_type, benchmark = fetch_handler(benchmark_handler_key)

    # Todo: handle generics better
    input_params: BaseModel = input_type.model_validate(bench_params)  # type: ignore[reportUnknownMemberType]
    assert isinstance(input_params, BaseModel)

    agent_bench = benchmark(input_params)

    if isinstance(dir, str):
        dir = Path(dir)

    experiment_path = dir / run_params.task_set.name / benchmark_handler_key / str(int(time.time()))

    experiment_path.mkdir(parents=True, exist_ok=True)
    _ = (experiment_path / "params.json").write_text(input_params.model_dump_json(indent=2))
    run_params.experiment_path = experiment_path

    # tasks are saved directly after being run
    _ = compute_tasks(agent_bench, run_params)
    return experiment_path


def main() -> None:
    parser = argparse.ArgumentParser(prog="NotteBench", description="Notte Benchmark tool for agents")
    _ = parser.add_argument("input_file", nargs="?", type=argparse.FileType("r"), default=sys.stdin)

    args = parser.parse_args()

    if args.input_file:
        # Data is from a file
        data = load_data(args.input_file)
        args.input_file.close()  # Good practice to close the file
    else:
        # Data is from stdin
        data = load_data()

    _ = run_tasks(data)


if __name__ == "__main__":
    main()
