from abc import ABC, abstractmethod

from notte_core.browser.observation import ExecutionResult, Observation, TrajectoryProgress
from notte_core.browser.snapshot import SnapshotMetadata
from notte_core.common.config import PerceptionType, config
from notte_core.data.space import DataSpace
from notte_core.space import ActionSpace


def trim_message(message: str, max_length: int | None = config.max_error_length) -> str:
    if max_length is None or len(message) <= max_length:
        return message
    return f"...{message[-max_length:]}"


class BasePerception(ABC):
    @property
    @abstractmethod
    def perception_type(self) -> PerceptionType:
        pass

    @abstractmethod
    def perceive_metadata(self, metadata: SnapshotMetadata, progress: TrajectoryProgress) -> str:
        pass

    @abstractmethod
    def perceive_actions(self, space: ActionSpace) -> str:
        pass

    @abstractmethod
    def perceive_data(self, data: DataSpace | None, only_structured: bool = True) -> str:
        pass

    @abstractmethod
    def perceive(self, obs: Observation, progress: TrajectoryProgress) -> str:
        pass

    @abstractmethod
    def perceive_action_result(
        self,
        result: ExecutionResult,
        include_ids: bool = False,
        include_data: bool = True,
    ) -> str:
        pass
