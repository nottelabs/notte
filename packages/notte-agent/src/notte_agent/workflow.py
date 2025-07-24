from typing import Any

from loguru import logger
from notte_browser.workflow_variables import Workflow
from notte_core.agent_types import AgentCompletion
from notte_sdk.types import AgentRunRequest
from typing_extensions import override

from notte_agent.agent import NotteAgent
from notte_agent.main import Agent


class WorkflowAgent(NotteAgent):
    def __init__(
        self,
        agent: Agent,
        path: str,
    ):
        self.agent: NotteAgent = agent.create_agent()  # pyright: ignore [reportAttributeAccessIssue]
        super().__init__(
            session=self.agent.session,
            prompt=self.agent.prompt,
            perception=self.agent.perception,
            config=self.agent.config,
            vault=self.agent.vault,
            trajectory=self.agent.trajectory,
        )
        with open(path, "r") as f:
            self.workflow: Workflow = Workflow.model_validate_json(f.read())

    @override
    async def observe_and_completion(self, request: AgentRunRequest) -> AgentCompletion:
        current_step = len(self.trajectory)
        nb_workflow_steps = len(self.workflow.steps)

        if current_step == 0 or (
            current_step >= nb_workflow_steps
            or self.trajectory.last_result is None
            or not self.trajectory.last_result.success
        ):
            logger.info("💨 Workflow - using agent mode to complete the trajectory")
            # if the trajectory is complete or the last step failed, reason about the next step
            if current_step == nb_workflow_steps and self.workflow.steps[-1].action.type != "completion":
                request.task = f"{request.task}\n\n CRITICAL: your next action should be a completion action."
            return await super().observe_and_completion(request)
        step = self.workflow.steps[current_step]
        logger.info(f"💨 Workflow - reusing workflow action '{step.action.type}'")
        return AgentCompletion(
            state=step.state,
            action=step.action,
        )

    @override
    async def arun(self, variables: dict[str, Any] | None = None):  # pyright: ignore [reportIncompatibleMethodOverride]
        _ = self.workflow.fill(variables)
        return await super().arun(**self.workflow.request.model_dump())
