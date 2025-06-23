from notte_browser.session import SessionTrajectoryStep
from notte_core.browser.observation import Observation, TrajectoryProgress
from pydantic import BaseModel, Field

from notte_agent.common.types import AgentStepResponse, AgentTrajectoryStep


class AgentTrajectoryHistory(BaseModel):
    max_steps: int
    steps: list[AgentTrajectoryStep] = Field(default_factory=list)

    def reset(self) -> None:
        self.steps = []

    def add_step(self, agent_response: AgentStepResponse, step: SessionTrajectoryStep) -> None:
        step.obs.progress = TrajectoryProgress(
            max_steps=self.max_steps,
            # +1 because we are adding the new step
            current_step=len(self.steps) + 1,
        )
        self.steps.append(
            AgentTrajectoryStep(
                agent_response=agent_response,
                action=step.action,
                obs=step.obs,
                result=step.result,
            )
        )

    def observations(self) -> list[Observation]:
        return [step.obs for step in self.steps]

    def last_obs(self) -> Observation:
        if len(self.steps) == 0:
            raise ValueError("No steps in trajectory")
        return self.steps[-1].obs
