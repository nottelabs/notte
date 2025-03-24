import json
import logging
import os
import typing

# posthog seems to deadlock tasks otherwise
os.environ["ANONYMIZED_TELEMETRY"] = "false"

from pydantic import BaseModel, SecretStr, ValidationError
from typing_extensions import override

from notte.utils.webp_replay import ScreenshotReplay
from notte_eval.agent_handlers import Proxy, trim_image_messages
from notte_eval.data.load_data import BenchmarkTask
from notte_eval.patcher import AgentPatcher, FunctionLog
from notte_eval.task_types import AgentBenchmark, LLMCall, Step, TaskResult
from notte_integrations.remote_sessions.anchor_pool import AnchorBrowserPool

try:
    from browser_use import Agent as BrowserUseAgent  # type: ignore
    from browser_use import AgentHistoryList, Browser, BrowserConfig  # type: ignore
    from browser_use.controller.views import DoneAction  # type: ignore
    from langchain_openai import ChatOpenAI
except ImportError:
    raise ImportError("Install notte[browseruse] to fix")


# solely for simplicity of parsing response
class BUAgentCurrentState(BaseModel):
    evaluation_previous_goal: str
    memory: str
    next_goal: str


class BUAgentArguments(BaseModel):
    current_state: BUAgentCurrentState
    action: list[dict[str, typing.Any]]


# used for the io to the benchmark (toml)
class BrowserUseInput(BaseModel):
    use_vision: bool
    model: str
    headless: bool
    max_steps: int
    use_anchor: bool
    proxy: Proxy | None = None


class BrowserUseOutput(BaseModel):
    logged_data: dict[str, list[FunctionLog]]
    per_step_calls: list[tuple[FunctionLog, dict[str, list[FunctionLog]]]]
    history: AgentHistoryList


class BrowserUseBench(AgentBenchmark[BrowserUseInput, BrowserUseOutput]):
    def __init__(self, params: BrowserUseInput):
        super().__init__(params)

    @override
    async def run_agent(self, task: BenchmarkTask) -> BrowserUseOutput:
        prompt = f"""You are a helpful web agent.
        Now you are given the task: {task.question}.
        Please interact with : {task.url or "the web"} to get the answer.
        """

        if self.params.proxy is not None:
            proxy = self.params.proxy.model_dump()
        else:
            proxy = None

        llm = ChatOpenAI(model=self.params.model, api_key=SecretStr(os.getenv("OPENAI_API_KEY", "")))

        pool = None
        wss_url = None
        if self.params.use_anchor:
            pool = AnchorBrowserPool()
            await pool.start()

            session = pool.create_session_cdp()
            wss_url = session.cdp_url

        context = None
        try:
            browser = Browser(config=BrowserConfig(headless=self.params.headless, cdp_url=wss_url, proxy=proxy))  # type: ignore
            context = await browser.new_context()
            agent = BrowserUseAgent(  # type: ignore
                browser=browser,
                browser_context=context,
                task=prompt,
                llm=llm,
                use_vision=self.params.use_vision,
            )

            patcher = AgentPatcher()
            _ = patcher.log(agent.llm, ["invoke", "ainvoke"])
            _ = patcher.log(agent, ["step", "run"])  # type: ignore

            result = await agent.run(max_steps=self.params.max_steps)
        finally:
            if context is not None:
                await context.close()
            if pool is not None:
                await pool.stop()

        return BrowserUseOutput(
            logged_data=patcher.logged_data,
            per_step_calls=patcher.find_encompassed_events("Agent.step"),
            history=result,
        )

    @override
    async def process_output(self, task: BenchmarkTask, out: BrowserUseOutput) -> TaskResult:
        len_steps = len(out.per_step_calls)
        len_history = len(out.history.history)

        if len_steps != len_history:
            logging.error(
                "Number of step calls isn't the same as the length in history:"
                + f"{len_steps=}, {len_history=}.\n"
                + "There will likely be a mismatch."
            )

        steps: list[Step] = []
        screenshots: list[str] = []
        for (step, in_step_calls), hist in zip(out.per_step_calls, out.history.history):
            screen = hist.state.screenshot
            if screen is not None:
                screenshots.append(screen)

            llm_calls: list[LLMCall] = []
            llm_calls_logs = in_step_calls["BaseChatModel.ainvoke"]
            for llm_call_log in llm_calls_logs:
                input_content = json.loads(llm_call_log.input_data)

                input_content = input_content["input"]

                # trim down images
                trim_image_messages(input_content)

                output_content = json.loads(llm_call_log.output_data)
                response = output_content["additional_kwargs"]
                tokens = output_content["response_metadata"]["token_usage"]

                message = ""
                try:
                    for tool_call in response["tool_calls"]:
                        if "function" not in tool_call or "arguments" not in tool_call["function"]:
                            continue

                        args = BUAgentArguments.model_validate_json(tool_call["function"]["arguments"])

                        message += f"🔎 {args.current_state.evaluation_previous_goal}\n"
                        message += f"🧠 {args.current_state.memory}\n"
                        message += f"🎯 {args.current_state.next_goal}\n"
                        message += "🛠️ Actions: \n"
                        for action in args.action:
                            message += f" - {action}\n"
                except ValidationError:
                    pass

                llm_calls.append(
                    LLMCall(
                        input_tokens=tokens["prompt_tokens"],
                        output_tokens=tokens["completion_tokens"],
                        messages_in=input_content,
                        message_out=response,
                        pretty_out=message,
                    )
                )

            # for llm_call in llm_calls:
            step = Step(
                url=hist.state.url,
                duration_in_s=step.duration_in_s,
                llm_calls=llm_calls,
            )
            steps.append(step)

        last_out = out.history.history[-1].model_output

        # default to the full string of the last output, otherwise pick out the answer if we can
        answer = str(last_out)
        try:
            if last_out is not None:
                for action in last_out.action:
                    if hasattr(action, "done"):
                        answer = typing.cast(DoneAction, getattr(action, "done")).text
                        break
        except Exception:
            answer = str(last_out)

        return TaskResult(
            success=out.history.is_successful() or False,
            duration_in_s=out.logged_data["Agent.run"][0].duration_in_s,
            agent_answer=answer,
            task=task,
            steps=steps,
            screenshots=ScreenshotReplay.from_base64(screenshots),
        )
