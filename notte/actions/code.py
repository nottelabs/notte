from dataclasses import dataclass
from typing import Final, Literal

import chevron
from patchright.async_api import Frame, Locator

from notte.actions.base import ActionParameterValue, ExecutableAction
from notte.browser.processed_snapshot import ProcessedBrowserSnapshot
from notte.errors.actions import InvalidActionError, MoreThanOneParameterActionError
from notte.errors.processing import InvalidInternalCheckError

TIMEOUT_MS: Final[int] = 1500


@dataclass
class LocatorResult:
    frame: Frame
    locator: Locator
    selector: str


def generate_playwright_code(action: ExecutableAction, context: ProcessedBrowserSnapshot) -> str:
    raise NotImplementedError("Not implemented")


async_code = """
async def execute_user_action(page: Page) -> bool:
    locator = page.locator(\"\"\"{{& selector}}\"\"\")
    try:
        await locator.{{action_type}}({{action_params}})
        return True
    except Exception as e:
        # last resort : try clicking
        try:
            await locator.click()
            return True
        except Exception as e:
            print(f"Error executing 'click' on selector '{{selector}}': {str(e)}")
            return False
"""

ActionType = Literal["click", "fill", "check", "select_option"]


def get_playwright_action(action: ExecutableAction) -> ActionType:

    if action.locator is None:
        raise InvalidActionError(action.id, "locator is to be able to execute an interaction action")
    role_str = action.locator.role if isinstance(action.locator.role, str) else action.locator.role.value
    match (action.id[0], role_str, action.locator.is_editable):
        case ("B", "button", _) | ("L", "link", _):
            return "click"
        case (_, _, True) | ("I", "textbox", _):
            return "fill"
        case ("I", "checkbox", _):
            return "check"
        case ("I", "combobox", _):
            return "select_option"
        case ("I", _, _):
            return "fill"
        case _:
            raise InvalidActionError(action.id, f"unknown action type: {action.id[0]}")


def get_action_params(action_type: ActionType, parameters: list[ActionParameterValue]) -> str:
    parameter_str = "timeout={TIMEOUT_MS}"
    match action_type:
        case "fill" | "select_option":
            if len(parameters) != 1:
                raise MoreThanOneParameterActionError(action_type, len(parameters))
            parameter_str = f"'{parameters[0].value}', {parameter_str}"
        case "check" | "click" | _:
            pass
    return parameter_str


# def get_playwright_code_from_selector(
#     selector: str,
#     action_type: str,
#     parameters: list[ActionParameterValue],
#     timeout: int = TIMEOUT_MS,
# ) -> str:
#     parameter_str = ""
#     match action_type:
#         case "fill" | "select_option":
#             if len(parameters) != 1:
#                 raise MoreThanOneParameterActionError(action_type, len(parameters))
#             parameter_str = f"'{parameters[0].value}',"
#         case "check" | "click" | _:
#             pass

#     return f"""async def execute_user_action(page: Page) -> bool:


#     if result is None:
#         print(f"[Action Execution Failed] No unique match found for selectors '{{selectors}}'")
#         return False

#     try:
#         await result.locator.{action_type}({parameter_str} timeout={timeout})
#         return True
#     except Exception as e:
#         print(f"Error executing {action_type} on selector '{{result.selector}}': {{str(e)}}")
#         return False
# """


def compute_playwright_code(
    action: ExecutableAction,
) -> str:
    locator = action.locator
    if locator is None:
        raise InvalidInternalCheckError(
            check=(
                f"Target Notte node resolution error for action {action.id}. "
                "Target node must be provided to create an executable action."
            ),
            url="unknown url",
            dev_advice=(
                "The node resolution pipeline should always be run before creating an executable action. "
                "Check the code in `notte.pipe.resolution.py`."
            ),
        )

    action_type = get_playwright_action(action)
    action_params = get_action_params(action_type, action.params_values)

    return chevron.render(
        template=async_code,
        data={
            "action_type": action_type,
            "action_params": action_params,
            "selector": locator.selector,
        },
    )


def process_action_code(
    action: ExecutableAction,
    context: ProcessedBrowserSnapshot,
    generated: bool = False,
) -> ExecutableAction:
    # fill code if it is not already cached
    if action.code is None:
        if generated:
            action_code = generate_playwright_code(action, context)
        else:
            action_code = compute_playwright_code(action)
        action.code = action_code
    return action
