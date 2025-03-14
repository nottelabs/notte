import json
from enum import StrEnum

from pydantic import BaseModel, field_validator
from typing_extensions import override

from notte.agents.falco.agent import (
    FalcoAgent,
    FalcoAgentConfig,
    HistoryType,
)
from notte.browser.pool.cdp_pool import SingleCDPBrowserPool
from notte.common.agent.config import RaiseCondition
from notte.common.agent.types import AgentResponse
from notte.utils.webp_replay import ScreenshotReplay
from notte_eval.agent_handlers import trim_image_messages
from notte_eval.data.load_data import BenchmarkTask
from notte_eval.patcher import AgentPatcher, FunctionLog
from notte_eval.task_types import AgentBenchmark, LLMCall, Step, TaskResult


class PoolEnum(StrEnum):
    NONE = "None"
    ANCHOR = "Anchor"
    STEEL = "Steel"
    BROWSERBASE = "BrowserBase"
    CAMOUFOX = "Camoufox"


class Proxy(BaseModel):
    server: str
    username: str
    password: str


class FalcoInput(BaseModel):
    use_vision: bool
    model: str
    max_steps: int
    history_type: str
    headless: bool = True
    proxy: Proxy | None = None
    pool: PoolEnum | str = PoolEnum("None")

    @field_validator("pool", mode="before")
    @classmethod
    def capitalize(cls, value: str) -> str:
        try:
            return PoolEnum(value)
        except:
            if value.startswith("wss://"):
                return value
            raise


class FalcoOutput(BaseModel):
    logged_data: dict[str, list[FunctionLog]]
    per_step_calls: list[tuple[FunctionLog, dict[str, list[FunctionLog]]]]
    output: AgentResponse


class ResultWithCode(TaskResult):
    replay_code: str

    @staticmethod
    def format_html_code(code: str) -> str:
        """Styler function to format code blocks in Pandas to_html()."""
        return (
            "<details>\n"
            "    <summary>Click to expand</summary>\n"
            '    <pre style="white-space: pre-wrap;"><code class="language-python">\n'
            f"{code}\n"
            "    </code></pre>\n"
            "</details>"
        )


class FalcoBench(AgentBenchmark[FalcoInput, FalcoOutput]):
    def __init__(self, params: FalcoInput):
        super().__init__(params)

    @override
    async def run_agent(self, task: BenchmarkTask) -> FalcoOutput:
        task_str = f"Your task: {task.question}. Use {task.url or 'the web'} to answer the question."

        if self.params.proxy is not None:
            proxy = self.params.proxy.model_dump()
        else:
            proxy = None

        config = FalcoAgentConfig(
            reasoning_model=self.params.model,
            raise_condition=RaiseCondition.NEVER,
            include_screenshot=self.params.use_vision,
            history_type=HistoryType(self.params.history_type),
        ).map_env(
            lambda env: env.steps(self.params.max_steps)
            .headless(self.params.headless)
            .llm_data_extract()
            .disable_web_security()
            .set_proxy(proxy)  # type: ignore
            ._copy_and_validate(perception_model=self.params.model)  # type: ignore
        )

        match self.params.pool:
            case PoolEnum.NONE:
                pool = None
            case PoolEnum.STEEL:
                from notte_integrations.remote_sessions.steel_pool import SteelBrowserPool

                pool = SteelBrowserPool(verbose=True)
                await pool.start()

            case PoolEnum.ANCHOR:
                from notte_integrations.remote_sessions.anchor_pool import AnchorBrowserPool

                pool = AnchorBrowserPool(verbose=True)
                await pool.start()

            case PoolEnum.BROWSERBASE:
                from notte_integrations.remote_sessions.browserbase_pool import BrowserBasePool

                pool = BrowserBasePool(verbose=True)
                await pool.start()

            case PoolEnum.CAMOUFOX:
                from notte_integrations.local_sessions.camoufox_pool import CamoufoxPool

                pool = CamoufoxPool(verbose=True)
                await pool.start()

            case _:
                pool = SingleCDPBrowserPool(cdp_url=self.params.pool)
                await pool.start()

        agent = FalcoAgent(config=config, pool=pool)
        patcher = AgentPatcher()
        _ = patcher.log(agent.llm, ["completion"])
        _ = patcher.log(agent, ["step", "run"])

        task_str = f"Your task: {task.question}. Use {task.url or 'the web'} to answer the question."
        try:
            output = await agent.run(task_str)
        finally:
            if pool is not None:
                await pool.stop()

        # need to do this to be able to pickle / serialize
        output.messages = json.loads(json.dumps(output.messages, default=str))
        for lusage in output.llm_usage:
            lusage.messages = json.loads(json.dumps(lusage.messages, default=str))

        return FalcoOutput(
            logged_data=patcher.logged_data,
            per_step_calls=patcher.find_encompassed_events("FalcoAgent.step"),
            output=output,
        )

    @override
    async def process_output(self, task: BenchmarkTask, out: FalcoOutput) -> TaskResult:
        steps: list[Step] = []
        screenshots: list[bytes] = []
        for (step, in_step_calls), hist in zip(out.per_step_calls, out.output.agent_trajectory):
            last_url = ""
            for res in hist.results:
                if res.success:
                    obs = res.get()
                    screen = obs.screenshot
                    if screen is not None:
                        screenshots.append(screen)

                    last_url = obs.metadata.url

            llm_calls: list[LLMCall] = []
            llm_calls_logs = in_step_calls["LLMEngine.completion"]
            for llm_call_log in llm_calls_logs:
                input_content = json.loads(llm_call_log.input_data)
                input_content = input_content["messages"]

                trim_image_messages(input_content)

                output_content = json.loads(llm_call_log.output_data)
                response = output_content["choices"][0]["message"]
                tokens = output_content["usage"]

                llm_calls.append(
                    LLMCall(
                        input_tokens=tokens["prompt_tokens"],
                        output_tokens=tokens["completion_tokens"],
                        messages_in=input_content,
                        message_out=response,
                    )
                )

            # for llm_call in llm_calls:
            step = Step(url=last_url, duration_in_s=step.duration_in_s, llm_calls=llm_calls)
            steps.append(step)

        return ResultWithCode(
            success=out.output.success,
            duration_in_s=out.logged_data["FalcoAgent.run"][0].duration_in_s,
            agent_answer=str(out.output.answer),
            task=task,
            steps=steps,
            screenshots=ScreenshotReplay.from_bytes(screenshots),
            replay_code=FalcoBench.format_code(out.output),
        )

    @staticmethod
    def format_code(agent_output: AgentResponse) -> str:
        LINE_TAG = "obs = await env.raw_step({action_name})"
        steps: list[str] = []
        for step in agent_output.agent_trajectory:
            for result in step.results:
                action = result.input
                action_name = f"{action.__class__.__name__}.model_validate({action.model_dump_json()})".replace(
                    "true", "True"
                ).replace("false", "False")
                steps.append(LINE_TAG.format(action_name=action_name))

        replay_steps = "\n".join(steps)
        return replay_steps
