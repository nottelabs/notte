from typing import Unpack, final

from loguru import logger

from notte.actions.base import Action, ActionParameterValue
from notte.actions.code import process_action_code
from notte.browser.context import Context, Observation
from notte.browser.driver import BrowserArgs, BrowserDriver
from notte.browser.snapshot import BrowserSnapshot
from notte.common.logging import timeit
from notte.common.parser import BaseNotteParser, Parser
from notte.common.resource import AsyncResource
from notte.llms.service import ModelRouter
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
        model: str | None = None,
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
        if model is not None:
            ModelRouter.set(model)

    # ---------------------------- observe, step functions ----------------------------

    async def _obslisting(self, snapshot: BrowserSnapshot, list_next: bool = True) -> Observation:
        self._context = BrowserSnapshotToContextPipe.forward(snapshot)
        space = None
        if list_next:
            space = await ContextToActionSpacePipe.forward(self._context, self.get_last_actions(snapshot))
        obs = Observation(url=snapshot.clean_url, screenshot=snapshot.screenshot, space=space)
        self._trajectory.append(obs)
        return obs

    async def _obs(self, url: str, list_next: bool = False) -> Observation:
        snapshot = await self._browser.goto(url)
        return await self._obslisting(snapshot, list_next)

    @timeit("goto")
    async def goto(self, url: str) -> Observation:
        return await self._obs(url, list_next=False)

    @timeit("observe")
    async def observe(self, url: str) -> Observation:
        snapshot = await self._browser.goto(url)
        return await self._obslisting(snapshot)

    async def _step(
        self,
        action_id: str,
        params: dict[str, str] | str | None = None,
        enter: bool | None = None,
        list_next: bool = True,
    ) -> Observation:
        if self._context is None:
            raise ValueError("Need to observe first to get a context.")
        action, _params = self._parse_env(action_id, params)
        enter = enter if enter is not None else action.id.startswith("I")
        snapshot = await ExecutionPipe.forward(action, _params, self._context, self._browser, enter=enter)
        return await self._obslisting(snapshot, list_next=list_next)

    @timeit("execute")
    async def execute(
        self,
        action_id: str,
        params: dict[str, str] | str | None = None,
        enter: bool | None = None,
    ) -> Observation:
        return await self._step(action_id, params, enter=enter, list_next=False)

    @timeit("step")
    async def step(
        self,
        action_id: str,
        params: dict[str, str] | str | None = None,
        enter: bool | None = None,
    ) -> Observation:
        return await self._step(action_id, params, enter, list_next=True)

    @timeit("reset")
    async def reset(self, url: str) -> Observation:
        self._trajectory = []
        self._context = None
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

    # ------------------------------ Getters ---------------------------------------

    def get_last_actions(self, snapshot: BrowserSnapshot) -> list[Action] | None:
        if len(self._trajectory) == 0:
            return None
        prev_obs: Observation = self._trajectory[-1]
        if snapshot.clean_url != prev_obs.url:
            return None
        if prev_obs.space is None:
            return None
        return prev_obs.space.actions(status=["valid", "failed", "excluded"])

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
