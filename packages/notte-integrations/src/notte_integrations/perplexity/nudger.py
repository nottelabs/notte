import json
import os
from typing import Any, Callable

import requests
from notte_agent.common.trajectory_history import TrajectoryHistory
from pydantic import BaseModel
from requests.sessions import Session

TASK_SYSTEM_PROMPT = """Break down web tasks into simple steps that a basic web ai agent can follow. For each task:
1) State the main goal in one sentence
2) Build 1-3 plans for how the task can be achieved
-> Those plans need to be quite simple: agents have a restricted action set, such as: click, type, scroll, or select
3) Use plain language and specify elements that might come up
4) Avoid complex reasoning or edge cases unless absolutely critical

Keep your entire response under 10 sentences. Focus only on the minimum actions needed.
Remember: The agent can only click, type, scroll, and select specific elements on a webpage.
"""

NUDGE_SYSTEM_PROMPT = """Help web ai agents solve simple problems by providing clear, direct guidance:

1) Identify any issue the agent might be facing in 1-2 sentences
2) Try to reason about simple fixes, or other approaches that the agent might have missed.
3) Suggest 1-2 simple alternative approaches that should be easily implementable

Your goal is to help in reasoning, think outside the box and challenge a bit the information that the original agent collected.
Do not focus on the technical aspect, your goal is to work similarly to a human with clear mind,
that can effortlessly navigate the web, but without deep technical knowledge.

Keep suggestions under 5 sentences each. Avoid complex explanations.
Always prioritize the simplest possible solution that will work.
The next messages will come from the web ai agent: help them solve their task.
"""


class PerplexityHelper:
    """Stateless, helper to make calls to perplexity"""

    def __init__(self, model: str = "sonar-pro"):
        ENV_VAR = "PERPLEXITY_API_KEY"
        self.api_key: str | None = os.getenv(ENV_VAR)
        self.model: str = model
        if self.api_key is None:
            raise ValueError(f"Set env variable {ENV_VAR}")

        self.session: Session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {self.api_key}"

    def task_breakdown(self, task: str) -> str:
        messages = [
            {"role": "system", "content": TASK_SYSTEM_PROMPT},
            {"role": "user", "content": f"The task is: {task}"},
        ]
        return self._ask_perplexity(messages)

    def nudge(self, task: str, agent_messages: list[dict[Any, Any]]) -> str:
        user_messages = [
            f"The task of the agent is: {task}",
            "\nThe following messages are all messages from the web ai agent that you need to help:",
        ]

        for message in agent_messages:
            content = message.get("content")
            role = message.get("role")
            if role != "system" and isinstance(content, str):
                user_messages.append(json.dumps(message))

        perplexity_messages = [
            {"role": "system", "content": NUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": "\n".join(user_messages)},
        ]
        return self._ask_perplexity(perplexity_messages)

    def _ask_perplexity(self, messages: list[dict[Any, Any]]) -> str:
        data = {"model": self.model, "messages": messages}
        resp = self.session.post("https://api.perplexity.ai/chat/completions", json=data)

        return resp.json()["choices"][0]["message"]["content"]


class PerplexityModule:
    """
    Call perplexity when agent struggles

    Parameters
    ----------
    model : str, default="sonar-pro"
        The name of the Perplexity model to use for processing.
    only_on_failure : bool, default=True
        When True, the module will only invoke the Perplexity API upon agent steps fail.
    min_step_interval : int, default=5
        The minimum number of steps agent has to make between API calls.
    """

    def __init__(
        self,
        model: str = "sonar-pro",
        only_on_failure: bool = True,
        min_step_interval: int = 5,
        failure_fn: Callable[..., bool] | None = None,
    ):
        """ """
        ENV_VAR = "PERPLEXITY_API_KEY"
        self.api_key: str | None = os.getenv(ENV_VAR)
        self.model: str = model
        if self.api_key is None:
            raise ValueError(f"Set env variable {ENV_VAR}")

        self.perplexity: PerplexityHelper = PerplexityHelper(model=self.model)
        self.last_step: int = 0
        self.only_on_failure: bool = only_on_failure
        self.min_step_interval: int = min_step_interval
        self.failure_fn: Callable[..., bool] | None = failure_fn

    def should_call(self, trajectory: TrajectoryHistory[BaseModel]):
        last_step_failed = not all(res.success for res in trajectory.steps[-1].results)
        current_step = len(trajectory.steps)
        enough_steps_passed = (current_step - self.last_step) > self.min_step_interval
        had_failure = self.failure_fn is not None and self.failure_fn()
        return enough_steps_passed and (had_failure or last_step_failed or not self.only_on_failure)

    def task_breakdown(self, task: str) -> str:
        return self.perplexity.task_breakdown(task)

    def nudge(self, task: str, trajectory: TrajectoryHistory[BaseModel], agent_messages: list[dict[Any, Any]]) -> str:
        self.last_step = len(trajectory.steps)
        return self.perplexity.nudge(task, agent_messages)
