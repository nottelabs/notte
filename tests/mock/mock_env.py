from typing import final

from typing_extensions import override

from notte.actions.base import Action
from notte.actions.space import ActionSpace
from notte.browser.observation import Observation
from notte.env import NotteEnv


@final
class MockNotteEnv(NotteEnv):
    """A mock version of NotteEnv that returns constant values for testing"""

    def __init__(self) -> None:
        super().__init__(headless=True, screenshot=False)
        self._mock_action = Action(description="Mock action", id="mock_id", category="mock", status="valid")
        self._mock_action_space = ActionSpace(
            _actions=[self._mock_action],
            description="Mock action space",
        )
        self._mock_observation = Observation(
            url="https://mock.url",
            title="Mock title",
            _space=self._mock_action_space,
        )

    @override
    async def observe(self, url: str | None = None) -> Observation:
        """Mock observe method that returns a constant observation"""
        return self._mock_observation

    @override
    async def step(
        self,
        action_id: Action | str,
        params: dict[str, str] | str | None = None,
        enter: bool | None = None,
    ) -> Observation:
        """Mock step method that returns a constant observation"""
        return self._mock_observation
