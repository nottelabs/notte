from notte.actions.base import ActionParameterValue, ExecutableAction
from notte.browser.context import Context
from notte.browser.node_type import HtmlSelector, NotteNode
from notte.errors.actions import InvalidActionError, MoreThanOneParameterActionError
from notte.errors.processing import InvalidInternalCheckError
from notte.errors.resolution import NodeResolutionAttributeError


def generate_playwright_code(action: ExecutableAction, context: Context) -> str:
    raise NotImplementedError("Not implemented")


async_code = """
async def execute_user_action(page: Page):
    await page.locator('{xpath}').{action_type}()
"""


def get_action_from_node(node: NotteNode) -> str:
    if node.id is None:
        raise InvalidInternalCheckError(
            check="node id is required to get action from node but is None",
            url=node.get_url(),
            dev_advice=(
                (
                    "This technnically should never happen. There is likely an issue during the snapshot "
                    "processing and/or the id generation."
                )
            ),
        )
    if node.attributes_post is None:
        raise NodeResolutionAttributeError(node, "post_attributes")
    match (node.id[0], node.get_role_str(), node.attributes_post.editable):
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
            raise InvalidActionError(node.id, f"unknown action type: {node.id[0]}")


def get_playwright_code_from_selector(
    selectors: HtmlSelector,
    action_type: str,
    parameters: list[ActionParameterValue],
    timeout: int = 1500,
) -> str:
    parameter_str = ""
    match action_type:
        case "fill" | "select_option":
            if len(parameters) != 1:
                raise MoreThanOneParameterActionError(action_type, len(parameters))
            parameter_str = f"'{parameters[0].value}',"
        case "check" | "click" | _:
            pass

    return f"""async def execute_user_action(page: Page) -> bool:
    selectors = [
        \"\"\"{selectors.playwright_selector}\"\"\",
        \"\"\"{selectors.css_selector}\"\"\",
        \"\"\"{selectors.xpath_selector}\"\"\"
    ]
    _locator = None
    for selector in selectors:
        for frame in page.frames:
            try:
                # Check if selector matches exactly one element
                locator = frame.locator(selector)
                count = await locator.count()
                if count == 1:
                    # Found unique match, perform click
                    await locator.{action_type}({parameter_str} timeout={timeout})
                    return True
            except Exception as e:
                print(f"Error with selector '{{selector}}' on frame '{{frame}}': {{str(e)}}, trying next...")
                continue
    # try one last click if a unique match is found
    if _locator is not None:
        try:
            await _locator.click(timeout={timeout})
            return True
        except Exception as e:
            print(f"Error with locator '{{_locator}}': {{str(e)}}, skipping...")
    print(f"[Action Execution Failed] No unique match found for selectors '{{selectors}}'")
    return False
"""


def compute_playwright_code(
    action: ExecutableAction,
) -> str:
    node = action.node
    if node is None:
        raise InvalidInternalCheckError(
            check=(
                (
                    f"Target Notte node resolution error for action {action.id}. "
                    "Target node must be provided to create an executable action."
                )
            ),
            url="unknown url",
            dev_advice=(
                (
                    "The node resolution pipeline should always be run before creating an executable action. "
                    "Check the code in `notte.pipe.resolution.py`."
                )
            ),
        )
    if node.attributes_post is None:
        raise NodeResolutionAttributeError(node, "post_attributes")
    selectors = node.attributes_post.selectors
    if selectors is None:
        raise NodeResolutionAttributeError(node, "selectors")

    action_type = get_action_from_node(node)

    return get_playwright_code_from_selector(selectors, action_type, parameters=action.params_values)


def process_action_code(
    action: ExecutableAction,
    context: Context,
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
