from loguru import logger
from notte_core.actions import (
    BaseAction,
    CheckAction,
    ClickAction,
    CompletionAction,
    FallbackFillAction,
    FillAction,
    GoBackAction,
    GoForwardAction,
    GotoAction,
    GotoNewTabAction,
    InteractionAction,
    MultiFactorFillAction,
    PressKeyAction,
    ReloadAction,
    ScrapeAction,
    ScrollDownAction,
    ScrollUpAction,
    SelectDropdownOptionAction,
    SwitchTabAction,
    WaitAction,
)
from notte_core.common.config import config
from notte_core.credentials.types import get_str_value
from notte_core.errors.actions import ActionExecutionError
from notte_core.utils.code import text_contains_tabs
from notte_core.utils.platform import platform_control_key
from patchright.async_api import Locator
from typing_extensions import final

from notte_browser.browser_dialog import BrowserDialogHandler
from notte_browser.dom.locate import locate_element
from notte_browser.errors import capture_playwright_errors
from notte_browser.window import BrowserWindow


@final
class BrowserController:
    def __init__(self, verbose: bool = False) -> None:
        self.verbose: bool = verbose

        self.execute = capture_playwright_errors(verbose=verbose)(self.execute)  # type: ignore[reportAttributeAccessIssue]

    async def switch_tab(self, window: BrowserWindow, tab_index: int) -> None:
        context = window.page.context
        if tab_index != -1 and (tab_index < 0 or tab_index >= len(context.pages)):
            raise ValueError(f"Tab index '{tab_index}' is out of range for context with {len(context.pages)} pages")
        tab_page = context.pages[tab_index]
        await tab_page.bring_to_front()
        window.page = tab_page
        await window.long_wait()
        if self.verbose:
            logger.info(
                f"🪦 Switched to tab {tab_index} with url: {tab_page.url} ({len(context.pages)} tabs in context)"
            )

    async def execute_browser_action(self, window: BrowserWindow, action: BaseAction) -> bool:
        match action:
            case GotoAction(url=url):
                await window.goto(url)
            case GotoNewTabAction(url=url):
                new_page = await window.page.context.new_page()
                window.page = new_page
                await window.goto(url=url)
            case SwitchTabAction(tab_index=tab_index):
                await self.switch_tab(window, tab_index)
            case WaitAction(time_ms=time_ms):
                await window.page.wait_for_timeout(time_ms)
            case GoBackAction():
                _ = await window.page.go_back()
            case GoForwardAction():
                _ = await window.page.go_forward()
            case ReloadAction():
                _ = await window.page.reload()
                await window.long_wait()
            case PressKeyAction(key=key):
                await window.page.keyboard.press(key)
            case ScrollUpAction(amount=amount):
                if amount is not None:
                    await window.page.mouse.wheel(delta_x=0, delta_y=-amount)
                else:
                    await window.page.keyboard.press("PageUp")
            case ScrollDownAction(amount=amount):
                if amount is not None:
                    await window.page.mouse.wheel(delta_x=0, delta_y=amount)
                else:
                    await window.page.keyboard.press("PageDown")
            case ScrapeAction():
                pass
            case _:
                raise ValueError(f"Unsupported action type: {type(action)}")
        return True

    async def execute_interaction_action(self, window: BrowserWindow, action: InteractionAction) -> bool:
        if window.active_dialog is not None:
            if action.id == BrowserDialogHandler.ACCEPT_ID:
                await window.active_dialog.accept()
            elif action.id == BrowserDialogHandler.DISMISS_ID:
                await window.active_dialog.dismiss()
            if action.id == BrowserDialogHandler.FILL_ID and isinstance(action, FillAction):
                await window.active_dialog.accept(prompt_text=get_str_value(action.value))

            window.active_dialog = None
            return True

        if action.selector is None:
            raise ValueError(f"Selector is required for {action.name()}")
        press_enter = False
        if action.press_enter is not None:
            press_enter = action.press_enter

        # locate element (possibly in iframe)
        locator: Locator = await locate_element(window.page, action.selector)
        original_url = window.page.url

        action_timeout = config.timeout_action_ms

        match action:
            # Interaction actions
            case ClickAction():
                await locator.click(timeout=action_timeout)
            case FillAction(value=value):
                if text_contains_tabs(text=get_str_value(value)):
                    if self.verbose:
                        logger.info(
                            "🪦 Indentation detected in fill action: simulating clipboard copy/paste for better string formatting"
                        )
                    await locator.focus()

                    if action.clear_before_fill:
                        await window.page.keyboard.press(key=f"{platform_control_key()}+A")
                        await window.short_wait()
                        await window.page.keyboard.press(key="Backspace")
                        await window.short_wait()

                    # Use isolated clipboard variable instead of system clipboard
                    await window.page.evaluate(
                        """
                        (text) => {
                            window.__isolatedClipboard = text;
                            const dataTransfer = new DataTransfer();
                            dataTransfer.setData('text/plain', window.__isolatedClipboard);
                            document.activeElement.dispatchEvent(new ClipboardEvent('paste', {
                                clipboardData: dataTransfer,
                                bubbles: true,
                                cancelable: true
                            }));
                        }
                    """,
                        value,
                    )

                    await window.short_wait()
                else:
                    await locator.fill(get_str_value(value), timeout=action_timeout, force=action.clear_before_fill)
                    await window.short_wait()
            case MultiFactorFillAction(value=value):
                # click the locator, then fill in one number at a time
                await locator.click()

                for num in get_str_value(value):
                    await window.page.keyboard.press(key=num)
                    await window.page.wait_for_timeout(100)
            case FallbackFillAction(value=value):
                await locator.click()
                await locator.press_sequentially(get_str_value(value))
                await window.short_wait()
            case CheckAction(value=value):
                if value:
                    await locator.check()
                else:
                    await locator.uncheck()
            case SelectDropdownOptionAction(value=value):
                # Check if it's a standard HTML select
                tag_name: str = await locator.evaluate("el => el.tagName.toLowerCase()")
                if tag_name == "select":
                    # Handle standard HTML select
                    _ = await locator.select_option(get_str_value(value))
                else:
                    try:
                        _ = await locator.click()
                    except Exception as e:
                        raise ActionExecutionError("select_dropdown", "", reason="Invalid selector") from e

            case _:
                raise ValueError(f"Unsupported action type: {type(action)}")
        if press_enter:
            if self.verbose:
                logger.info(f"🪦 Pressing enter for action {action.id}")
                await window.short_wait()
            await window.page.keyboard.press("Enter")
        if original_url != window.page.url:
            if self.verbose:
                logger.info(f"🪦 Page navigation detected for action {action.id} waiting for networkidle")
            await window.long_wait()

        return True

    async def execute(self, window: BrowserWindow, action: BaseAction) -> bool:
        context = window.page.context
        num_pages = len(context.pages)
        retval = True
        match action:
            case InteractionAction():
                retval = await self.execute_interaction_action(window, action)
            case CompletionAction(success=success, answer=answer):
                if self.verbose:
                    logger.info(
                        f"Completion action: status={'success' if success else 'failure'} with answer = {answer}"
                    )
            case _:
                retval = await self.execute_browser_action(window, action)
        # add short wait before we check for new tabs to make sure that
        # the page has time to be created
        await window.short_wait()
        if len(context.pages) != num_pages:
            if self.verbose:
                logger.info(f"🪦 Action {action.id} resulted in a new tab, switched to it...")
            await self.switch_tab(window, -1)
        return retval
