import argparse
import asyncio
import concurrent
import concurrent.futures
import contextlib
import io
import logging
import time
import tomllib
import traceback
from pathlib import Path
from typing import Any

import cloudpickle
from loguru import logger as loguru_logger
from pydantic import BaseModel
from typing_extensions import override

# auto import handlers
import examples.benchmark.handlers  # noqa: F401
from eval.webvoyager.load_data import (
    WebVoyagerSubset,
    WebVoyagerTask,
    load_webvoyager_data,
)
from examples.benchmark.default import (
    AgentBenchmark,
    AgentOut,
    AgentParams,
    LoggingSink,
    TaskResult,
)
from examples.benchmark.evaluators import Evaluator
from examples.benchmark.registry import BenchmarkRegistry, EvaluatorRegistry
from examples.benchmark.screenshots import Screenshots


class RunParameters(BaseModel):
    n_jobs: int
    tries_per_task: int
    evaluator: Evaluator | None = None


class InRunParameters(BaseModel):

    class Config:
        frozen = True

    run_id: int
    evaluator: Evaluator | None = None


def setup_logging(log_stream):
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
    agent_bench: AgentBenchmark[AgentParams, AgentOut], task: WebVoyagerTask, inrun_params: InRunParameters
) -> bytes:

    loguru_logger.remove()
    sink = LoggingSink()
    _ = loguru_logger.add(sink, level="DEBUG")  # Redirect loguru logs

    log_capture = io.StringIO()
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()

    setup_logging(log_capture)

    with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stderr_capture):
        run = await agent_bench.run_agent(task)
        out = await agent_bench.process_output(task, run)

        out.run_id = inrun_params.run_id

        if inrun_params.evaluator is not None:
            out.eval = await inrun_params.evaluator.eval(
                out.agent_answer, task.question, out.screenshots.b64_screenshots
            )

    out.logs["stdout"] = stdout_capture.getvalue()
    out.logs["stderr"] = stderr_capture.getvalue()
    out.logs["logging"] = log_capture.getvalue()
    out.logs["loguru"] = "\n".join(sink.messages)

    with open("run.pkl", "wb") as f:
        cloudpickle.dump((task, run, out), f)

    return cloudpickle.dumps((task, run, out))


def compute_tasks(
    agent_bench: AgentBenchmark[AgentParams, AgentOut], run_parameters: RunParameters
) -> list[tuple[WebVoyagerTask, AgentOut, TaskResult]]:
    tasks = load_webvoyager_data(WebVoyagerSubset.Simple)

    inputs = [
        (agent_bench, task, InRunParameters(run_id=run_id, evaluator=run_parameters.evaluator))
        for task in tasks[:10]
        for run_id in range(run_parameters.tries_per_task)
    ]

    # gather intermediate steps (agent outputs)
    with concurrent.futures.ProcessPoolExecutor(max_workers=run_parameters.n_jobs) as executor:
        loop = asyncio.get_event_loop()
        futures = [loop.run_in_executor(executor, sync_wrapper, *inp) for inp in inputs]
        gathered_outs = loop.run_until_complete(asyncio.gather(*futures))

    return [cloudpickle.loads(output) for output in gathered_outs]


def sync_wrapper(
    agent_bench: AgentBenchmark[AgentParams, AgentOut], task: WebVoyagerTask, inrun_params: InRunParameters
) -> bytes:
    """Wrapper for async function to run in a process."""
    try:
        loop = asyncio.new_event_loop()
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


class MockInput(BaseModel):
    a: int
    b: bool


class MockOutput(BaseModel):
    s: str


class MockBench(AgentBenchmark[MockInput, MockOutput]):

    def __init__(self, params: MockInput):
        super().__init__(params)

    @override
    async def run_agent(self, task: WebVoyagerTask) -> MockOutput:
        return MockOutput(s=str(self.params.a))

    @override
    async def process_output(self, task: WebVoyagerTask, out: MockOutput) -> TaskResult:
        return TaskResult(
            duration_in_s=0, agent_answer=out.s, task=task, steps=[], screenshots=Screenshots.from_base64([])
        )


def save_task(root_path: Path, task_res: TaskResult):

    path = root_path / f"{task_res.task_website}_{task_res.task_id}" / str(task_res.run_id)

    path.mkdir(parents=True, exist_ok=True)

    with open(path / "res_dump.json", "w") as f:
        _ = f.write(task_res.model_dump_json(indent=2))

    with open(path / "summary.webp", "wb") as f:
        _ = f.write(task_res.screenshots.summary_webp(start_text=task_res.task.question))


def main() -> None:
    RUN_PARAMS_KEY = "RunParameters"

    parser = argparse.ArgumentParser(prog="NotteBench", description="Notte Benchmark tool for agents")
    parser.add_argument("filename", type=str, help="Param filename")

    args = parser.parse_args()

    name_to_benchmark = BenchmarkRegistry.get_all_classes()
    name_to_eval = EvaluatorRegistry.get_all_classes()

    with open(args.filename, "rb") as f:
        data = tomllib.load(f)

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

    input_type: type[BaseModel] | None = None
    bench_params: dict[str, Any] | None = None
    benchmark: type[AgentBenchmark[Any, Any]] | None = None
    agent_key: str | None = None

    benchmark, bench_params, input_type = None, None, None
    for key in data:
        if key not in name_to_benchmark:
            raise ValueError(f"No benchmark for {key}")

        input_type, benchmark = name_to_benchmark[key]
        bench_params = data[key]
        agent_key = key

    if benchmark is None or input_type is None or bench_params is None or agent_key is None:
        raise ValueError("Please provide table with parameters to benchmark")

    input_params: BaseModel = input_type.model_validate(bench_params)
    agent_bench = benchmark(input_params)

    experiment_path = Path(".") / "webvoyager" / agent_key / str(int(time.time()))

    experiment_path.mkdir(parents=True, exist_ok=True)
    _ = (experiment_path / "params.json").write_text(input_params.model_dump_json(indent=2))

    task_results = compute_tasks(agent_bench, run_params)
    for _, _, res in task_results:
        save_task(experiment_path, res)


if __name__ == "__main__":
    main()
