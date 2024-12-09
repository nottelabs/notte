from notte.actions.base import ActionParameterValue, ExecutableAction
from notte.browser.context import Context
from notte.browser.node_type import HtmlSelector, NotteNode


def generate_playwright_code(action: ExecutableAction, context: Context) -> str:
    raise NotImplementedError("Not implemented")


async_code = """
async def execute_user_action(page: Page):
    await page.locator('{xpath}').{action_type}()
"""


def get_action_from_node(node: NotteNode) -> str:
    if node.id is None:
        raise ValueError("Node id is required to get action from node")
    if node.attributes_post is None:
        raise ValueError("Node attributes are required to get action from node")
    match (node.id[0], node.get_role_str(), node.attributes_post.editable):
        case ("B", "button", _):
            return "click"
        case (_, _, True) | ("I", "textbox", _):
            return "fill"
        case ("L", "link", _):
            return "click"
        case ("I", "checkbox", _):
            return "check"
        case ("I", "combobox", _):
            return "select_option"
        case ("I", _, _):
            return "fill"
        case _:
            raise ValueError(f"Unknown action type: {node.id[0]}")


def get_playwright_code_from_selector(
    selectors: HtmlSelector,
    action_type: str,
    parameters: list[ActionParameterValue],
) -> str:
    parameter_str = ""
    execute_command = ""
    match action_type:
        case "fill":
            if len(parameters) != 1:
                raise ValueError(f"Fill action must have 1 parameter but got {parameters}")
            parameter_str = f"'{parameters[0].value}'"
            # execute_command = "await locator.press('Enter')"
        case "select_option":
            parameter_str = f"'{parameters[0].value}'"
        case "check" | "click" | _:
            pass

    return f"""async def execute_user_action(page: Page):
    selectors = [
        \"\"\"{selectors.playwright_selector}\"\"\",
        \"\"\"{selectors.css_selector}\"\"\",
        \"\"\"{selectors.xpath_selector}\"\"\"
    ]
    _locator = None
    for selector in selectors:
        try:
            # Check if selector matches exactly one element
            count = await page.locator(selector).count()

            if count == 1:
                # Found unique match, perform click
                locator = page.locator(selector)
                _locator = locator
                await locator.{action_type}({parameter_str})
                {execute_command}
                return
        except Exception as e:

            print(f"Error with selector '{{selector}}': {{str(e)}}, trying next...")
            continue
    # try one last click if a unique match is found
    if _locator is not None:
        try:
            await _locator.click()
            return
        except Exception as e:
            print(f"Error with locator '{{_locator}}': {{str(e)}}, skipping...")
    print(f"No unique match found for selectors '{{selectors}}'")
"""


def compute_playwright_code(
    action: ExecutableAction,
) -> str:
    node = action.node
    if node is None:
        raise ValueError(f"Target Notte node for action {action.id} must be provided")
    if node.attributes_post is None:
        raise ValueError("Selectors are required to compute action code")
    selectors = node.attributes_post.selectors
    if selectors is None:
        raise ValueError("Selectors are required to compute action code")

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
