from notte_browser.session import SessionTrajectoryStep
from notte_core.browser.observation import Observation, TrajectoryProgress
from pydantic import BaseModel, Field

from notte_agent.common.types import AgentStepResponse, AgentTrajectoryStep


class AgentTrajectoryHistory(BaseModel):
    max_steps: int
    steps: list[AgentTrajectoryStep] = Field(default_factory=list)

    def reset(self) -> None:
        self.steps = []

    #     def perceive(self) -> str:
    #         steps = "\n".join([self.perceive_step(step, step_idx=i) for i, step in enumerate(self.steps)])
    #         return f"""
    # [Start of action execution history memory]
    # {steps or self.start_rules()}
    # [End of action execution history memory]
    #     """

    #     def perceive_step(
    #         self,
    #         step: AgentTrajectoryStep,
    #         step_idx: int = 0,
    #         include_ids: bool = False,
    #         include_data: bool = True,
    #     ) -> str:
    #         action_msg = "\n".join(["  - " + result.action.model_dump_agent_json() for result in step.results])
    #         status_msg = "\n".join(
    #             ["  - " + self.perceive_step_result(result, include_ids, include_data) for result in step.results]
    #         )
    #         return f"""
    # # Execution step {step_idx}
    # * state:
    #     - page_summary: {step.agent_response.state.page_summary}
    #     - previous_goal_status: {step.agent_response.state.previous_goal_status}
    #     - previous_goal_eval: {step.agent_response.state.previous_goal_eval}
    #     - memory: {step.agent_response.state.memory}
    #     - next_goal: {step.agent_response.state.next_goal}
    # * selected actions:
    # {action_msg}
    # * execution results:
    # {status_msg}"""

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
