import json
from typing import TypedDict

from loguru import logger
from playwright.async_api import Page

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
                    logger.debug(f'Dropdown ID: {options["id"]}, Name: {options["name"]}')

                    formatted_options: list[str] = []
                    for opt in options["options"]:
                        # encoding ensures AI uses the exact string in select_dropdown_option
                        encoded_text = json.dumps(opt["text"])
                        formatted_options.append(f'{opt["index"]}: text={encoded_text}')

                    all_options.extend(formatted_options)

            except Exception as frame_e:
                logger.debug(f"Frame {frame_index} evaluation failed: {str(frame_e)}")

            frame_index += 1

        return all_options
    except Exception as e:
        logger.error(f"Error getting dropdown menu options: {str(e)}")
        return []
