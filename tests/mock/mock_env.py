from typing import final

from notte.actions.base import Action
from notte.actions.space import ActionSpace
from notte.browser.context import Observation
from notte.env import NotteEnv
from typing_extensions import override


@final
class MockNotteEnv(NotteEnv):
    """A mock version of NotteEnv that returns constant values for testing"""

    def __init__(self) -> None:
        super().__init__(headless=True, screenshot=False)
        self._mock_action = Action(description="Mock action", id="mock_id", category="mock", status="valid")
        self._mock_action_space = ActionSpace(
            _actions=[self._mock_action],
        )
        self._mock_observation = Observation(url="https://mock.url", screenshot=None, space=self._mock_action_space)

    @override
    async def observe(self, url: str, observe_next: bool = True) -> Observation:
        """Mock observe method that returns a constant observation"""
        return self._mock_observation

    @override
    async def step(
        self,
        action: Action | str,
        value: str | None = None,
        list_next: bool = False,
    ) -> Observation:
        """Mock step method that returns a constant observation"""
        return self._mock_observation
