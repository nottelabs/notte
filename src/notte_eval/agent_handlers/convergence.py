import json
import logging
import re
from typing import Any

from pydantic import BaseModel
from typing_extensions import override

from notte.utils.webp_replay import ScreenshotReplay
from notte_eval.agent_handlers import Proxy, trim_image_messages
from notte_eval.data.load_data import BenchmarkTask
from notte_eval.patcher import AgentPatcher, FunctionLog
from notte_eval.task_types import AgentBenchmark, LLMCall, Step, TaskResult
from notte_integrations.remote_sessions.anchor_pool import AnchorBrowserPool

try:
    from proxy_lite import Runner, RunnerConfig  # type: ignore
    from proxy_lite.runner import Run  # type: ignore
    from proxy_lite.solvers import SimpleSolver  # type: ignore
except ImportError:
    raise ImportError("Install with notte[convergence] to include convergence benchmark integration")


class ConvergenceInput(BaseModel):
    max_steps: int
    api_base: str = "https://convergence-ai-demo-api.hf.space/v1"
    headless: bool
    use_anchor: bool
    proxy: Proxy | None = None


class ConvergenceOutput(BaseModel):
    logged_data: dict[str, list[FunctionLog]]
    per_step_calls: list[tuple[FunctionLog, dict[str, list[FunctionLog]]]]
    run: Run


class ConvergenceBench(AgentBenchmark[ConvergenceInput, ConvergenceOutput]):
    def __init__(self, params: ConvergenceInput):
        super().__init__(params)

    @override
    async def run_agent(self, task: BenchmarkTask) -> ConvergenceOutput:
        prompt = f"""You are a helpful web agent.
        Now you are given the task: {task.question}.
        Please interact with : {task.url or "the web"} to get the answer.
        """
        pool = None

        if self.params.use_anchor:
            pool = AnchorBrowserPool()
            await pool.start()

            session = pool.create_session_cdp()
            wss_url = session.cdp_url
        else:
            wss_url = None

        if self.params.proxy is not None:
            proxy = self.params.proxy.model_dump()
        else:
            proxy = None

        config = RunnerConfig.from_dict(  # type: ignore
            {
                "environment": {
                    "name": "webbrowser",
                    "homepage": "https://www.google.com",
                    "headless": self.params.headless,  # Don't show the browser
                    "cdp_url": wss_url,
                    "proxy": proxy,
                },
                "solver": {
                    "name": "simple",
                    "agent": {
                        "name": "proxy_lite",
                        "client": {
                            "name": "convergence",
                            "model_id": "convergence-ai/proxy-lite-3b",
                            "api_base": self.params.api_base,
                        },
                    },
                },
                "max_steps": self.params.max_steps,
                "action_timeout": 1800,
                "environment_timeout": 1800,
                "task_timeout": 18000,
                "logger_level": "DEBUG",
            },
        )

        agent = Runner(config=config)

        patcher = AgentPatcher()

        self.solver: SimpleSolver | None = None

        def get_solver_cb(kwargs: dict[str, Any]) -> None:
            if self.solver is not None:
                return

            solver = kwargs["self"]
            _ = patcher.log(solver.agent.client, ["create_completion"])
            self.solver = solver

        _ = patcher.log(agent, ["run_generator", "run"])
        _ = patcher.log(agent.solver, ["act"], pre_callback=get_solver_cb)

        try:
            result = await agent.run(prompt)
        finally:
            if pool is not None:
                await pool.stop()

        return ConvergenceOutput(
            logged_data=patcher.logged_data,
            per_step_calls=patcher.find_encompassed_events("SimpleSolver.act"),
            run=result,
        )

    @override
    async def process_output(self, task: BenchmarkTask, out: ConvergenceOutput) -> TaskResult:
        steps: list[Step] = []
        screenshots: list[str] = []
        for act_call, completion_calls in out.per_step_calls:
            obs = json.loads(act_call.input_data)

            url = obs["observation"]["info"]["url"]

            screenshots.append(obs["observation"]["state"]["image"])
            duration_in_s = 0

            llm_calls: list[LLMCall] = []

            logging.warning(f"completion calls: {completion_calls}, keys: {out.logged_data.keys()}\n")

            for completion_call in completion_calls.get("ConvergenceClient.create_completion", []):
                input_data = json.loads(completion_call.input_data)
                output_data = json.loads(completion_call.output_data)

                token_usage = output_data["usage"]
                in_tokens = token_usage["prompt_tokens"]
                out_tokens = token_usage["completion_tokens"]

                input_content = input_data["messages"]["messages"]
                trim_image_messages(input_content)

                def parse_tags(regex: str, content: str, default: str = "") -> str:
                    match = re.search(regex, content, re.DOTALL)
                    return match.group(1).strip() if match else default

                response = output_data["choices"][0]["message"]
                content = response["content"]
                obs = parse_tags(r"<observation>(.*?)</observation>", content, "No observation")
                thought = parse_tags(r"<thinking>(.*?)</thinking>", content, "No thought")

                message = ""
                message += f"🔎 {obs}\n"
                message += f"🧠 {thought}\n"
                message += "🛠️ Actions: \n"
                for tool_call in response["tool_calls"]:
                    message += f" - {json.dumps(tool_call['function'])}\n"

                llm_calls.append(
                    LLMCall(
                        messages_in=input_content,
                        message_out=response,
                        input_tokens=in_tokens,
                        output_tokens=out_tokens,
                        pretty_out=message,
                    )
                )

            steps.append(Step(url=url, duration_in_s=duration_in_s, llm_calls=llm_calls))

        duration_in_s = out.logged_data["Runner.run"][0].duration_in_s

        return TaskResult(
            success=out.run.complete,
            duration_in_s=duration_in_s,
            agent_answer=out.run.result or "No result",
            task=task,
            steps=steps,
            screenshots=ScreenshotReplay.from_base64(screenshots),
        )
