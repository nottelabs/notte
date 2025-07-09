from loguru import logger
from notte_core.actions import ActionList, ActionUnion
from notte_core.agent_types import AgentState, AgentStepResponse
from typing_extensions import override

from notte_agent.agent import NotteAgent
from notte_agent.main import Agent


class Workflow(NotteAgent):
    def __init__(
        self,
        agent: Agent,
        steps: list[ActionUnion] | None = None,
        path: str | None = None,
    ):
        self.agent: NotteAgent = agent.create_agent()  # pyright: ignore [reportAttributeAccessIssue]
        super().__init__(
            session=self.agent.session,
            prompt=self.agent.prompt,
            perception=self.agent.perception,
            config=self.agent.config,
            vault=self.agent.vault,
            step_callback=self.agent.step_callback,
        )
        self.actions: list[ActionUnion] = []
        match steps, path:
            case (None, None):
                raise ValueError("Either steps or path must be provided")
            case None, _:
                with open(path, "r") as f:
                    self.actions = ActionList.model_validate_json(f.read()).actions
            case [[], None]:
                raise ValueError("steps cannot be empty")
            case _, None:
                self.actions = steps
            case _, _:
                raise ValueError("Only one of steps or path must be provided")

    @override
    async def reason(self, task: str) -> AgentStepResponse:
        first_step = len(self.trajectory) == 0
        if first_step or (len(self.trajectory) >= len(self.actions) or not self.trajectory.last_result().success):
            logger.info("💨 Workflow - using agent mode to complete the trajectory")
            # if the trajectory is complete or the last step failed, reason about the next step
            if len(self.trajectory) == len(self.actions) and self.actions[-1].type != "completion":
                task = f"{task}\n\n CRITICAL: your next action should be a completion action."
            return await super().reason(task)
        action = self.actions[len(self.trajectory)]
        logger.info(f"💨 Workflow - reusing workflow action '{action.type}'")
        return AgentStepResponse(
            state=AgentState(
                previous_goal_status="success",
                previous_goal_eval="completed",
                page_summary=self.trajectory.last_obs().metadata.title if first_step else "no observation so far",
                relevant_interactions=[],
                memory="No memory",
                next_goal="",
            ),
            action=action,
        )
