from abc import ABC, abstractmethod


class BasePrompt(ABC):
    @abstractmethod
    def system(self) -> str:
        pass

    @abstractmethod
    def task(self, task: str) -> str:
        pass

    @abstractmethod
    def select_action(self) -> str:
        pass

    @abstractmethod
    def empty_trajectory(self) -> str:
        pass
