import argparse
import asyncio
import concurrent
import concurrent.futures
import contextlib
import io
import logging
import sys
import time
import tomllib
import traceback
from pathlib import Path
from typing import TextIO

import cloudpickle
from loguru import logger as loguru_logger
from pydantic import BaseModel

from notte_eval.agent_handlers import fetch_handler
from notte_eval.evaluators.evaluator import Evaluator
from notte_eval.registry import EvaluatorRegistry
from notte_eval.task_types import (
    AgentBenchmark,
    AgentOut,
    AgentParams,
    LoggingSink,
    TaskResult,
)
from notte_eval.webvoyager.load_data import (
    WebVoyagerSubset,
    WebVoyagerTask,
    load_webvoyager_data,
)


class RunParameters(BaseModel):
    n_jobs: int
    tries_per_task: int
    task_set: WebVoyagerSubset
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


async def run_agent(
    agent_bench: AgentBenchmark[AgentParams, AgentOut],
    task: WebVoyagerTask,
    inrun_params: InRunParameters,
) -> bytes:
    log_capture = io.StringIO()
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()

    loguru_logger.remove()
    sink = LoggingSink()

    if inrun_params.capture_logging:
        _ = loguru_logger.add(sink, level="DEBUG")  # Redirect loguru logs

        setup_logging(log_capture)
    else:
        stdout_capture = sys.stdout
        stderr_capture = sys.stderr

    with (
        contextlib.redirect_stdout(stdout_capture),
        contextlib.redirect_stderr(stderr_capture),
    ):
        run = await agent_bench.run_agent(task)
        out = await agent_bench.process_output(task, run)

        out.run_id = inrun_params.run_id

        if inrun_params.evaluator is not None:
            out.eval = await inrun_params.evaluator.eval(
                out.agent_answer, task.question, out.screenshots.b64_screenshots
            )

        save_task(inrun_params.experiment_path, out)

    if inrun_params.capture_logging:
        assert isinstance(stderr_capture, io.StringIO) and isinstance(stdout_capture, io.StringIO)

        out.logs["stdout"] = stdout_capture.getvalue()
        out.logs["stderr"] = stderr_capture.getvalue()
        out.logs["logging"] = log_capture.getvalue()
        out.logs["loguru"] = "\n".join(sink.messages)

    return cloudpickle.dumps((task, run, out))  # type: ignore[reportUnknownMemberType]


def compute_tasks(
    agent_bench: AgentBenchmark[AgentParams, AgentOut], run_parameters: RunParameters
) -> list[tuple[WebVoyagerTask, AgentOut, TaskResult]]:
    tasks = load_webvoyager_data(WebVoyagerSubset.Simple)

    inputs = [
        (
            agent_bench,
            task,
            InRunParameters(
                run_id=run_id,
                evaluator=run_parameters.evaluator,
                experiment_path=run_parameters.experiment_path,
                capture_logging=run_parameters.capture_logging,
            ),
        )
        for task in tasks
        for run_id in range(run_parameters.tries_per_task)
    ]

    if run_parameters.n_jobs == 1:
        gathered_outs = [sync_wrapper(*inp) for inp in inputs]

    else:
        with concurrent.futures.ProcessPoolExecutor(max_workers=run_parameters.n_jobs) as executor:
            loop = asyncio.get_event_loop()
            futures = [loop.run_in_executor(executor, sync_wrapper, *inp) for inp in inputs]
            gathered_outs = loop.run_until_complete(asyncio.gather(*futures))

    final_outs: list[tuple[WebVoyagerTask, AgentOut, TaskResult]] = []
    for out in gathered_outs:
        try:
            task_outputs = cloudpickle.loads(out)
            final_outs.append(task_outputs)
        except Exception as e:
            logging.error(f"Could not load output from cloudpickle: {e}")

    return final_outs


def sync_wrapper(
    agent_bench: AgentBenchmark[AgentParams, AgentOut],
    task: WebVoyagerTask,
    inrun_params: InRunParameters,
) -> bytes:
    """Wrapper for async function to run in a process."""
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(run_agent(agent_bench, task, inrun_params))
        return result
    except Exception as e:
        logging.warning(f"Exception {e}\n{traceback.format_exc()}")
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
        asyncio.set_event_loop(None)

    return b""


def save_task(root_path: str | Path, task_res: TaskResult):
    if not isinstance(root_path, Path):
        path = Path(root_path)
    else:
        path = root_path

    path = path / f"{task_res.task_website}_{task_res.task_id}" / str(task_res.run_id)

    path.mkdir(parents=True, exist_ok=True)

    with open(path / "res_dump.json", "w") as f:
        _ = f.write(task_res.model_dump_json(indent=2))

    with open(path / "summary.webp", "wb") as f:
        _ = f.write(task_res.screenshots.summary_webp(start_text=task_res.task.question))


def load_data(input_stream: TextIO | None = None):
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


def main() -> None:
    RUN_PARAMS_KEY = "RunParameters"

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

    name_to_eval = EvaluatorRegistry.get_all_classes()

    if RUN_PARAMS_KEY not in data:
        raise ValueError("Need to configure run with RunParameters table")

    run_params_dict = data[RUN_PARAMS_KEY]
    evaluator = run_params_dict["evaluator"]

    if evaluator == "None":
        run_params_dict["evaluator"] = None
    elif evaluator not in name_to_eval:
        raise ValueError(f"No evaluator found for {evaluator}")
    else:
        run_params_dict["evaluator"] = name_to_eval[evaluator]()

    run_params = RunParameters.model_validate(run_params_dict)

    del data[RUN_PARAMS_KEY]

    if len(data) > 1:
        raise ValueError("Table should only have params for a single Agent")

    benchmark_handler_key = next(iter(data.keys()))
    bench_params = data[benchmark_handler_key]
    input_type, benchmark = fetch_handler(benchmark_handler_key)

    # Todo: handle generics better
    input_params: BaseModel = input_type.model_validate(bench_params)  # type: ignore[reportUnknownMemberType]
    assert isinstance(input_params, BaseModel)

    agent_bench = benchmark(input_params)

    experiment_path = Path(".") / "webvoyager" / benchmark_handler_key / str(int(time.time()))

    experiment_path.mkdir(parents=True, exist_ok=True)
    _ = (experiment_path / "params.json").write_text(input_params.model_dump_json(indent=2))
    run_params.experiment_path = experiment_path

    # tasks are saved directly after being run
    _ = compute_tasks(agent_bench, run_params)


if __name__ == "__main__":
    main()
