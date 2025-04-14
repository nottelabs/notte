from abc import ABC, abstractmethod


class BasePrompt(ABC):
    @abstractmethod
    def system(self) -> str:
        pass

    @abstractmethod
    def output_format_rules(self) -> str:
        pass

    @abstractmethod
    def select_action_rules(self) -> str:
        pass
