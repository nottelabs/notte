import json

# not a fan of this messing with logs
# can't just call it upon use, as we need it for the type def
from browser_use import Agent as BrowserUseAgent
from browser_use import AgentHistoryList, Browser, BrowserConfig
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from typing_extensions import override

from eval.patcher import AgentPatcher, FunctionLog
from eval.webvoyager.load_data import WebVoyagerTask
from examples.benchmark.default import AgentBenchmark, LLMCall, Step, TaskResult
from examples.benchmark.registry import BenchmarkRegistry
from examples.benchmark.screenshots import Screenshots


class BrowserUseInput(BaseModel):
    use_vision: bool
    model: str
    headless: bool
    max_steps: int


class BrowserUseOutput(BaseModel):

    logged_data: dict[str, list[FunctionLog]]
    per_step_calls: list[tuple[FunctionLog, dict[str, list[FunctionLog]]]]
    history: AgentHistoryList


@BenchmarkRegistry.register("BrowserUse", BrowserUseInput)
class BrowserUseBench(AgentBenchmark[BrowserUseInput, BrowserUseOutput]):

    def __init__(self, params: BrowserUseInput):
        super().__init__(params)

    @override
    async def run_agent(self, task: WebVoyagerTask) -> BrowserUseOutput:
        prompt = f"""You are a helpful web agent.
        Now you are given the task: {task.question}.
        Please interact with : {task.url or "the web"} to get the answer.
        """

        llm = ChatOpenAI(
            model=self.params.model,
            temperature=0,
        )
        browser = Browser(
            config=BrowserConfig(
                headless=self.params.headless,
            )
        )
        agent = BrowserUseAgent(
            browser=browser,
            task=prompt,
            llm=llm,
            use_vision=self.params.use_vision,
        )

        patcher = AgentPatcher()
        _ = patcher.log(agent.llm, ["invoke", "ainvoke"])
        _ = patcher.log(agent, ["step", "run"])
        result = await agent.run(max_steps=self.params.max_steps)
        return BrowserUseOutput(
            logged_data=patcher.logged_data,
            per_step_calls=patcher.find_encompassed_events("Agent.step"),
            history=result,
        )

    @override
    async def process_output(self, task: WebVoyagerTask, out: BrowserUseOutput) -> TaskResult:

        len_steps = len(out.per_step_calls)
        len_history = len(out.history.history)

        assert len_steps == len_history
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

                input_content = [inp["kwargs"] for inp in input_content["input"]]
                output_content = json.loads(llm_call_log.output_data)
                response = output_content["additional_kwargs"]
                tokens = output_content["response_metadata"]["token_usage"]

                llm_calls.append(
                    LLMCall(
                        input_tokens=tokens["prompt_tokens"],
                        output_tokens=tokens["completion_tokens"],
                        messages_in=input_content,
                        message_out=response,
                    )
                )

            # for llm_call in llm_calls:
            step = Step(url=hist.state.url, duration_in_s=step.duration_in_s, llm_calls=llm_calls)
            steps.append(step)

        return TaskResult(
            duration_in_s=out.logged_data["Agent.run"][0].duration_in_s,
            agent_answer=str(out.history.history[-1].model_output),
            task=task,
            steps=steps,
            screenshots=Screenshots.from_base64(screenshots),
        )
