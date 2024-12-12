from typing import Unpack, final

from loguru import logger

from notte.actions.base import Action, ActionParameterValue
from notte.actions.code import process_action_code
from notte.actions.space import ActionSpace
from notte.browser.context import Context, Observation
from notte.browser.driver import BrowserArgs, BrowserDriver
from notte.browser.snapshot import BrowserSnapshot
from notte.common.logging import timeit
from notte.common.parser import BaseNotteParser, Parser
from notte.common.resource import AsyncResource
from notte.pipe.main import ContextToActionSpacePipe
from notte.pipe.preprocessing.a11y.pipe import ActionA11yPipe
from notte.pipe.resolution import ActionNodeResolutionPipe


@final
class BrowserSnapshotToContextPipe:
    @staticmethod
    def forward(snapshot: BrowserSnapshot) -> Context:
        return ActionA11yPipe.forward(snapshot)


@final
class ExecutionPipe:
    @staticmethod
    async def forward(
        action: Action,
        params: list[ActionParameterValue],
        context: Context,
        browser: BrowserDriver,
        enter: bool = False,
    ) -> BrowserSnapshot:
        exec_actions = await ActionNodeResolutionPipe(browser).forward(action, params, context)
        action = process_action_code(exec_actions, context, generated=False)
        return await browser.execute_action(action, context, enter)


class NotteEnv(AsyncResource):
    def __init__(
        self,
        browser: BrowserDriver | None = None,
        trajectory: list[Observation] | None = None,
        parser: Parser | None = None,
        **browser_kwargs: Unpack[BrowserArgs],
    ) -> None:
        self._browser: BrowserDriver = browser or BrowserDriver(**browser_kwargs)
        super().__init__(self._browser)
        self._trajectory: list[Observation] = trajectory or []
        self._parser: Parser = parser or BaseNotteParser()
        self._context: Context | None = None
        self._action_space: ActionSpace | None = None
        self._context_to_action_space_pipe: ContextToActionSpacePipe = ContextToActionSpacePipe()

    @property
    def context(self) -> Context:
        if self._context is None:
            raise ValueError("Need to observe first to get a context.")
        return self._context

    @property
    def list_actions(self) -> list[Action] | None:
        if self._action_space is None:
            return None
        if len(self._trajectory) >= 2 and self._trajectory[-1].clean_url != self._trajectory[-2].clean_url:
            # If the last two observations are not on the same page, the last action space is invalid.
            return None
        return self._action_space.actions(status="all")

    # ---------------------------- observe, step functions ----------------------------

    async def _observe(self, snapshot: BrowserSnapshot) -> Observation:
        self._context = BrowserSnapshotToContextPipe.forward(snapshot)
        obs = Observation(url=snapshot.url, screenshot=snapshot.screenshot, space=None)
        self._trajectory.append(obs)
        return obs

    @timeit("goto")
    async def goto(self, url: str) -> Observation:
        snapshot = await self._browser.goto(url)
        self._action_space = None
        return await self._observe(snapshot)

    @timeit("observe")
    async def observe(self, url: str) -> Observation:
        snapshot = await self._browser.goto(url)
        obs = await self._observe(snapshot)
        self._action_space = await self._context_to_action_space_pipe.forward(self.context, self.list_actions)
        obs.space = self._action_space
        return obs

    async def _execute(
        self,
        action_id: str,
        params: dict[str, str] | str | None = None,
        enter: bool | None = None,
    ) -> Observation:
        if self._context is None:
            raise ValueError("Need to observe first to get a context.")
        action, _params = self._parse_env(action_id, params)
        enter = enter if enter is not None else action.id.startswith("I")
        snapshot = await ExecutionPipe.forward(action, _params, self._context, self._browser, enter=enter)
        return await self._observe(snapshot)

    @timeit("execute")
    async def execute(
        self,
        action_id: str,
        params: dict[str, str] | str | None = None,
        enter: bool | None = None,
    ) -> Observation:
        self._action_space = None
        return await self._execute(action_id, params, enter=enter)

    @timeit("step")
    async def step(
        self,
        action_id: str,
        params: dict[str, str] | str | None = None,
        enter: bool | None = None,
    ) -> Observation:
        obs = await self._execute(action_id, params, enter=enter)
        self._action_space = await self._context_to_action_space_pipe.forward(self.context, self.list_actions)
        obs.space = self._action_space
        return obs

    @timeit("reset")
    async def reset(self, url: str) -> Observation:
        self._trajectory = []
        self._context = None
        self._action_space = None
        return await self.observe(url)

    # ---------------------------- conversational environment ----------------------------

    async def chat(self, text: str) -> str:
        endpoint = self._parser.which(text)
        logger.debug(f"picking {endpoint} endpoint")
        if endpoint == "observe":
            observe_params = self._parser.observe(text)
            obs = await self.observe(observe_params.url)
            return self._parser.textify(obs)
        elif endpoint == "step":
            step_params = self._parser.step(text)
            obs = await self.step(step_params.action_id, step_params.params, enter=False)
            return self._parser.textify(obs)
        return self._parser.rules()

    # ------------------------------ Private ---------------------------------------

    def _parse_env(
        self, action_id: str, params: dict[str, str] | str | None = None
    ) -> tuple[Action, list[ActionParameterValue]]:
        if isinstance(params, str):
            params = {"value": params}
        _params: list[ActionParameterValue] = []
        if params is not None:
            _params = [
                ActionParameterValue(
                    parameter_name=name,
                    value=value,
                )
                for name, value in params.items()
            ]
        return (
            Action(id=action_id, description="ID only", category="", status="valid"),
            _params,
        )
