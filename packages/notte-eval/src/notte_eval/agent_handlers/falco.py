import json
from typing import Any

from notte_agent.common.types import AgentResponse
from notte_agent.falco.agent import FalcoAgent
from notte_browser.session import NotteSession
from notte_core.utils.webp_replay import ScreenshotReplay
from notte_sdk.types import ProxySettings
from pydantic import BaseModel, ValidationError
from typing_extensions import override

from notte_eval.agent_handlers import trim_image_messages
from notte_eval.data.load_data import BenchmarkTask
from notte_eval.patcher import AgentPatcher, FunctionLog
from notte_eval.task_types import AgentBenchmark, LLMCall, Step, TaskResult


# solely for parsing the model output
class FalcoState(BaseModel):
    page_summary: str
    relevant_interactions: list[dict[str, Any]]
    previous_goal_status: str
    previous_goal_eval: str
    memory: str
    next_goal: str


class FalcoResponse(BaseModel):
    state: FalcoState
    actions: list[dict[str, Any]]


# useful for io to bench
class FalcoInput(BaseModel):
    use_vision: bool
    model: str
    max_steps: int
    headless: bool = True
    proxies: list[ProxySettings] | bool
    user_agent: str | None = None


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
        async with NotteSession(headless=self.params.headless, proxies=self.params.proxies) as session:
            agent = FalcoAgent(
                session=session,
                reasoning_model=self.params.model,
                use_vision=self.params.use_vision,
                max_steps=self.params.max_steps,
            )
            patcher = AgentPatcher()
            _ = patcher.log(agent.llm, ["completion"])
            _ = patcher.log(agent, ["step", "run"])

            output = await agent.run(task=f"Your task: {task.question}", url=task.url)
        # need to do this to be able to pickle / serialize
        output.llm_messages = json.loads(json.dumps(output.llm_messages, default=str))
        assert output.llm_usage is not None
        for lusage in output.llm_usage.steps:
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
        for (step, in_step_calls), hist in zip(out.per_step_calls, out.output.trajectory.step_iterator()):
            last_url = ""
            if hist.observation is not None:
                obs = hist.observation
                screen = obs.screenshot
                screenshots.append(screen.bytes())

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

                message = ""
                try:
                    args = FalcoResponse.model_validate_json(response["content"])
                    message += f"📋 {args.state.page_summary}\n"
                    message += f"🔎 {args.state.previous_goal_eval}\n"
                    message += f"🧠 {args.state.memory}\n"
                    message += f"🎯 {args.state.next_goal}\n"
                    if len(args.state.relevant_interactions) > 0:
                        message += "👆 Interactables:\n"
                        for interact in args.state.relevant_interactions:
                            message += f" - {interact}\n"
                    message += "🛠️ Actions: \n"
                    for action in args.actions:
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
            step = Step(url=last_url, duration_in_s=step.duration_in_s, llm_calls=llm_calls)
            steps.append(step)

        if "NotteAgent.run" not in out.logged_data:
            raise ValueError(
                f"NotteAgent.run not found in logged data. Valid keys are: {', '.join(out.logged_data.keys())}"
            )

        return ResultWithCode(
            success=out.output.success,
            duration_in_s=out.logged_data["NotteAgent.run"][0].duration_in_s,
            agent_answer=str(out.output.answer),
            task=task,
            steps=steps,
            screenshots=ScreenshotReplay.from_bytes(screenshots),
            replay_code=FalcoBench.format_code(out.output),
        )

    @staticmethod
    def format_code(agent_output: AgentResponse) -> str:
        LINE_TAG = "obs = await env.aexecute(action={action_name})"
        steps: list[str] = []
        for step in agent_output.trajectory.execution_results():
            action = step.action
            action_name = action.model_dump()
            steps.append(LINE_TAG.format(action_name=action_name))

        replay_steps = "\n".join(steps)
        return replay_steps
