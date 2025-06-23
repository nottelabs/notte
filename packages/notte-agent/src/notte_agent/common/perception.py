from abc import ABC, abstractmethod

from notte_browser.session import SessionTrajectoryStep
from notte_core.browser.observation import Observation
from notte_core.common.config import config


def trim_message(message: str, max_length: int | None = config.max_error_length) -> str:
    if max_length is None or len(message) <= max_length:
        return message
    return f"...{message[-max_length:]}"


class BasePerception(ABC):
    @abstractmethod
    def perceive_metadata(self, obs: Observation) -> str:
        pass

    @abstractmethod
    def perceive_actions(self, obs: Observation) -> str:
        pass

    @abstractmethod
    def perceive_data(self, obs: Observation, only_structured: bool = True) -> str:
        pass

    @abstractmethod
    def perceive(self, obs: Observation) -> str:
        pass

    @abstractmethod
    def perceive_action_result(
        self,
        step: SessionTrajectoryStep,
        include_ids: bool = False,
        include_data: bool = False,
    ) -> str:
        pass
