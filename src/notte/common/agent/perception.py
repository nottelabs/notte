from abc import ABC, abstractmethod

from notte.browser.observation import Observation


class BasePerception(ABC):
    @abstractmethod
    def perceive_metadata(self, obs: Observation) -> str:
        pass

    @abstractmethod
    def perceive_actions(self, obs: Observation) -> str:
        pass

    @abstractmethod
    def perceive_data(self, obs: Observation) -> str:
        pass

    @abstractmethod
    def perceive(self, obs: Observation) -> str:
        pass
