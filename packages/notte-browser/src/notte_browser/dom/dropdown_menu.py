import json

from loguru import logger
from typing_extensions import TypedDict

from notte_browser.playwright_async_api import Page

# TODO: refactor this


class DropdownMenuOptions(TypedDict):
    text: str
    value: str
    index: int


class DropdownMenu(TypedDict):
    options: list[DropdownMenuOptions]
    id: str
    name: str


async def dropdown_menu_options(page: Page, selector: str) -> list[str]:
    try:
        # Frame-aware approach since we know it works
        all_options: list[str] = []
        frame_index = 0

        for frame in page.frames:
            try:
                options: DropdownMenu = await frame.evaluate(
                    """
(xpath) => {
    const select = document.evaluate(xpath, document, null,
        XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
    if (!select) return null;

    return {
        options: Array.from(select.options).map(opt => ({
            text: opt.text, //do not trim, because we are doing exact match in select_dropdown_option
            value: opt.value,
            index: opt.index
        })),
        id: select.id,
        name: select.name
    };
}
                """,
                    selector,
                )

                if options:
                    logger.debug(f"Found dropdown in frame {frame_index}")
                    logger.debug(f"Dropdown ID: {options['id']}, Name: {options['name']}")

                    formatted_options: list[str] = []
                    for opt in options["options"]:
                        # encoding ensures AI uses the exact string in select_dropdown_option
                        encoded_text = json.dumps(opt["text"])
                        formatted_options.append(f"{opt['index']}: text={encoded_text}")

                    all_options.extend(formatted_options)

            except Exception as frame_e:
                logger.debug(f"Frame {frame_index} evaluation failed: {str(frame_e)}")

            frame_index += 1

        return all_options
    except Exception as e:
        logger.debug(f"Error getting dropdown menu options: {str(e)}")
        return []


async def select_dropdown_option(
    page: Page,
    tag_name: str,
    xpath: str,
    text: str,
) -> str:
    """Select dropdown option by the text of the option you want to select"""

    # Validate that we're working with a select element
    if tag_name != "select":
        logger.debug(f"Element is not a select! Tag: {tag_name}")
        msg = f"Cannot select option: Element with a {tag_name} tag, not a select"
        return msg

    logger.debug(f"Attempting to select '{text}' using xpath: {xpath}")
    logger.debug(f"Element tag: {tag_name}")

    _xpath = "//" + xpath

    try:
        frame_index = 0
        for frame in page.frames:
            try:
                logger.debug(f"Trying frame {frame_index} URL: {frame.url}")

                # First verify we can find the dropdown in this frame
                find_dropdown_js = """
(xpath) => {
    try {
        const select = document.evaluate(xpath, document, null,
            XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
        if (!select) return null;
        if (select.tagName.toLowerCase() !== 'select') {
            return {
                error: `Found element but it's a ${select.tagName}, not a SELECT`,
                found: false
            };
        }
        return {
            id: select.id,
            name: select.name,
            found: true,
            tagName: select.tagName,
            optionCount: select.options.length,
            currentValue: select.value,
            availableOptions: Array.from(select.options).map(o => o.text.trim())
        };
    } catch (e) {
        return {error: e.toString(), found: false};
    }
}
                """

                dropdown_info = await frame.evaluate(find_dropdown_js, xpath)

                if dropdown_info:
                    if not dropdown_info.get("found"):
                        logger.debug(f"Frame {frame_index} error: {dropdown_info.get('error')}")
                        continue

                    logger.debug(f"Found dropdown in frame {frame_index}: {dropdown_info}")

                    # "label" because we are selecting by text
                    # nth(0) to disable error thrown by strict mode
                    # timeout=1000 because we are already waiting for all network events, therefore
                    # ideally we don't need to wait a lot here (default 30s)
                    select_element = frame.locator(_xpath).nth(0)
                    selected_option_values = await select_element.select_option(label=text, timeout=1000)

                    msg = f"selected option {text} with value {selected_option_values}"
                    logger.trace(msg + f" in frame {frame_index}")

                    return msg

            except Exception as frame_e:
                logger.debug(f"Frame {frame_index} attempt failed: {str(frame_e)}")
                logger.debug(f"Frame type: {type(frame)}")
                logger.debug(f"Frame URL: {frame.url}")

            frame_index += 1

        msg = f"Could not select option '{text}' in any frame"
        logger.trace(msg)
        return msg

    except Exception as e:
        msg = f"Selection failed: {str(e)}"
        logger.debug(msg)
        return msg
