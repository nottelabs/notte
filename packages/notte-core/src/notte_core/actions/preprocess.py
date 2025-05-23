import abc
import typing
from collections.abc import Callable

from notte_browser.dom.locate import locate_element
from notte_browser.resolution import NodeResolutionPipe
from patchright.async_api import Locator, Page
from typing_extensions import override

from notte_core.actions.verifier import ActionVerifier
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.controller.actions import (
    BaseAction,
    InteractionAction,
)
from notte_core.credentials.base import BaseVault, LocatorAttributes
from notte_core.errors.base import NotteBaseError


class ExecData(typing.NamedTuple):
    action: BaseAction
    err: NotteBaseError | None

    @staticmethod
    def get_action(value: "BaseAction | ExecData") -> BaseAction:
        if isinstance(value, BaseAction):
            return value
        action, _ = value
        return action

    @staticmethod
    def get_error(value: "BaseAction | ExecData") -> NotteBaseError | None:
        if isinstance(value, BaseAction):
            return None
        _, err = value
        return err


class ActionPreprocessor(abc.ABC):
    async def forward(
        self, snapshot: BrowserSnapshot, page: Page, action: BaseAction | tuple[BaseAction, NotteBaseError | None]
    ) -> ExecData:
        """If previously got action, continue, otherwise pass on original action and error"""

        if isinstance(action, tuple):
            action, err = action

            if err is not None:
                return ExecData(action, err)

        out = await self._forward(snapshot, page, action)
        if isinstance(out, NotteBaseError):
            return ExecData(action, out)
        else:
            return ExecData(out, None)

    async def _forward(self, snapshot: BrowserSnapshot, page: Page, action: BaseAction) -> BaseAction | NotteBaseError:  # pyright: ignore [reportUnusedParameter]
        raise NotImplementedError

    @staticmethod
    async def action_locator(snapshot: BrowserSnapshot, page: Page, action: BaseAction) -> Locator | None:
        action_with_selector = await NodeResolutionPipe.forward(action, snapshot)
        if isinstance(action_with_selector, InteractionAction) and action_with_selector.selector is not None:
            return await locate_element(page, action_with_selector.selector)
        return None


class VaultActionError(NotteBaseError):
    pass


class VaultPreprocessor(ActionPreprocessor):
    def __init__(self, vault: BaseVault) -> None:
        self.vault: BaseVault = vault

    @staticmethod
    async def compute_locator_attributes(locator: Locator) -> LocatorAttributes:
        attr_type = await locator.get_attribute("type")
        autocomplete = await locator.get_attribute("autocomplete")
        outer_html = await locator.evaluate("el => el.outerHTML")
        return LocatorAttributes(type=attr_type, autocomplete=autocomplete, outerHTML=outer_html)

    @override
    async def _forward(self, snapshot: BrowserSnapshot, page: Page, action: BaseAction) -> BaseAction | NotteBaseError:
        if self.vault.contains_credentials(action):
            locator = await ActionPreprocessor.action_locator(snapshot, page, action)

            if locator is None:
                dev_message = (
                    "Action contained credentials to replace, but could not get locator, try a different action"
                )
                user_message = f"Could not replace credentials for {action}"

                return VaultActionError(dev_message=dev_message, agent_message=dev_message, user_message=user_message)

            attrs = await VaultPreprocessor.compute_locator_attributes(locator)
            return self.vault.replace_credentials(
                action,
                attrs,
                snapshot,
            )
        return action


class LLMActionVerifierError(NotteBaseError):
    pass


@typing.final
class LLMVerifierPreprocessor(ActionPreprocessor):
    def __init__(self, reasoning_model: str, use_vision: bool, goal_function: Callable[..., str | None]) -> None:
        self.reasoning_model = reasoning_model
        self.use_vision = use_vision
        self.goal_function = goal_function

    @override
    async def _forward(self, snapshot: BrowserSnapshot, page: Page, action: BaseAction) -> BaseAction | NotteBaseError:
        # action check thingy
        goal = self.goal_function()
        if goal is None:
            return action

        locator = await ActionPreprocessor.action_locator(snapshot, page, action)
        if locator is None:
            return action

        act_check = ActionVerifier(self.reasoning_model, self.use_vision)
        check = await act_check.verify_locator(goal, locator)
        if not check.valid:
            dev_message = f"After further verification, the ID {action.id} doesn't match the current goal: {goal}. Reason: {check.reason}. Try picking a different action or ID."
            user_message = "Invalid action picked by agent: retrying"
            return LLMActionVerifierError(dev_message=dev_message, agent_message=dev_message, user_message=user_message)

        return action
