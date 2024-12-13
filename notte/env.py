from typing import Unpack, final

from loguru import logger

from notte.actions.base import Action, ActionParameterValue
from notte.actions.code import process_action_code
from notte.browser.context import Context
from notte.browser.driver import BrowserArgs, BrowserDriver
from notte.browser.observation import Observation, PreObservation
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
        # This function is always called after trajectory.append(preobs)
        # —This means trajectory[-1] is always the "current (pre)observation"
        # And trajectory[-2] is the "previous observation" we're interested in.
        if len(self._trajectory) <= 1:
            return None
        previous_obs: Observation = self._trajectory[-2]
        if isinstance(previous_obs, PreObservation):
            return None  # we don't have a space for pre-observations
        if self.context.snapshot.clean_url != previous_obs.clean_url:
            return None  # the page has significantly changed
        return previous_obs.space.actions(status="all")

    # ---------------------------- observe, step functions ----------------------------

    def _preobserve(self, snapshot: BrowserSnapshot) -> PreObservation:
        self._context = BrowserSnapshotToContextPipe.forward(snapshot)
        preobs = PreObservation(_url=snapshot.url, _screenshot=snapshot.screenshot, _space=None)
        self._trajectory.append(preobs)
        return preobs

    def _obslisting(self, preobs: PreObservation) -> Observation:
        space = self._context_to_action_space_pipe.forward(self.context, self.previous_actions)
        obs = Observation(_url=preobs.url, _screenshot=preobs.screenshot, _space=space)
        self._trajectory[-1] = obs  # update the last observation with the new space
        return obs

    @timeit("goto")
    async def goto(self, url: str) -> PreObservation:
        snapshot = await self._browser.goto(url)
        obs = self._preobserve(snapshot)
        return obs

    @timeit("observe")
    async def observe(self, url: str) -> Observation:
        preobs = await self.goto(url)
        logger.debug(f"ℹ️ previous actions IDs: {[a.id for a in self.previous_actions or []]}")
        logger.debug(f"ℹ️ context inodes IDs: {[node.id for node in self.context.interaction_nodes()]}")
        return self._obslisting(preobs)

    @timeit("execute")
    async def execute(
        self,
        action_id: str,
        params: dict[str, str] | str | None = None,
        enter: bool | None = None,
    ) -> PreObservation:
        if action_id not in [inode.id for inode in self.context.interaction_nodes()]:
            raise ValueError(f"action {action_id} not found in context")
        action, _params = self._parse_env(action_id, params)
        enter = enter if enter is not None else action.id.startswith("I")
        snapshot = await ExecutionPipe.forward(action, _params, self.context, self._browser, enter=enter)
        logger.info(f"🌌 action {action_id} executed in browser")
        return self._preobserve(snapshot)

    @timeit("step")
    async def step(
        self,
        action_id: str,
        params: dict[str, str] | str | None = None,
        enter: bool | None = None,
    ) -> Observation:
        preobs = await self.execute(action_id, params, enter=enter)
        logger.debug(f"ℹ️ previous actions IDs: {[a.id for a in self.previous_actions or []]}")
        logger.debug(f"ℹ️ context inodes IDs: {[node.id for node in self.context.interaction_nodes()]}")
        return self._obslisting(preobs)

    @timeit("reset")
    async def reset(self, url: str) -> PreObservation:
        self._trajectory = []
        self._context = None
        return await self.goto(url)

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
