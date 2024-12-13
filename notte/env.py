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
from notte.llms.service import LLMService
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
        llmserve: LLMService | None = None,
        **browser_kwargs: Unpack[BrowserArgs],
    ) -> None:
        self._browser: BrowserDriver = browser or BrowserDriver(**browser_kwargs)
        super().__init__(self._browser)
        self._trajectory: list[Observation] = trajectory or []
        self._parser: Parser = parser or BaseNotteParser()
        self._context: Context | None = None
        self._context_to_action_space_pipe: ContextToActionSpacePipe = ContextToActionSpacePipe(
            llmserve=llmserve,
        )

    @property
    def context(self) -> Context:
        if self._context is None:
            raise ValueError("Need to observe first to get a context.")
        return self._context

    @property
    def previous_actions(self) -> list[Action] | None:
        if len(self._trajectory) == 0:
            return None
        previous_obs: Observation = self._trajectory[-1]
        if self.context.snapshot.clean_url != previous_obs.clean_url:
            return None
        if previous_obs.space is None:
            return None
        return previous_obs.space.actions(status="all")

    # ---------------------------- observe, step functions ----------------------------

    async def _preobserve(self, snapshot: BrowserSnapshot) -> Observation:
        self._context = BrowserSnapshotToContextPipe.forward(snapshot)
        obs = Observation(url=snapshot.url, screenshot=snapshot.screenshot, space=None)
        self._trajectory.append(obs)
        return obs

    @timeit("goto")
    async def goto(self, url: str) -> Observation:
        snapshot = await self._browser.goto(url)
        obs = await self._preobserve(snapshot)
        return obs

    @timeit("observe")
    async def observe(self, url: str) -> Observation:
        obs = await self.goto(url)
        obs.space = self._context_to_action_space_pipe.forward(self.context, self.previous_actions)
        return obs

    @timeit("execute")
    async def execute(
        self,
        action_id: str,
        params: dict[str, str] | str | None = None,
        enter: bool | None = None,
    ) -> Observation:
        action, _params = self._parse_env(action_id, params)
        enter = enter if enter is not None else action.id.startswith("I")
        snapshot = await ExecutionPipe.forward(action, _params, self.context, self._browser, enter=enter)
        return await self._preobserve(snapshot)

    @timeit("step")
    async def step(
        self,
        action_id: str,
        params: dict[str, str] | str | None = None,
        enter: bool | None = None,
    ) -> Observation:
        obs = await self.execute(action_id, params, enter=enter)
        obs.space = self._context_to_action_space_pipe.forward(self.context, self.previous_actions)
        return obs

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
            obs = await self.step(step_params.action_id, step_params.params)
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
