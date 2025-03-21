from loguru import logger
from patchright.async_api import Locator
from typing_extensions import final

from notte.browser.snapshot import BrowserSnapshot
from notte.browser.window import BrowserWindow
from notte.controller.actions import (
    BaseAction,
    CheckAction,
    ClickAction,
    CompletionAction,
    FillAction,
    GoBackAction,
    GoForwardAction,
    GotoAction,
    GotoNewTabAction,
    InteractionAction,
    ListDropdownOptionsAction,
    PressKeyAction,
    ReloadAction,
    ScrapeAction,
    ScrollDownAction,
    ScrollUpAction,
    SelectDropdownOptionAction,
    SwitchTabAction,
    WaitAction,
)
from notte.errors.handler import capture_playwright_errors
from notte.pipe.preprocessing.dom.dropdown_menu import dropdown_menu_options
from notte.pipe.preprocessing.dom.locate import locale_element
from notte.utils.code import text_contains_tabs
from notte.utils.platform import platform_control_key


@final
class BrowserController:
    def __init__(self, window: BrowserWindow, verbose: bool = False) -> None:
        self.window: BrowserWindow = window
        self.verbose: bool = verbose

        self.execute = capture_playwright_errors(verbose=verbose)(self.execute)  # type: ignore[reportAttributeAccessIssue]

    async def switch_tab(self, tab_index: int) -> None:
        context = self.window.page.context
        if tab_index != -1 and (tab_index < 0 or tab_index >= len(context.pages)):
            raise ValueError(f"Tab index '{tab_index}' is out of range for context with {len(context.pages)} pages")
        tab_page = context.pages[tab_index]
        await tab_page.bring_to_front()
        self.window.page = tab_page
        await self.window.long_wait()
        if self.verbose:
            logger.info(
                f"🪦 Switched to tab {tab_index} with url: {tab_page.url} ({len(context.pages)} tabs in context)"
            )

    async def execute_browser_action(self, action: BaseAction) -> BrowserSnapshot | None:
        match action:
            case GotoAction(url=url):
                return await self.window.goto(url)
            case GotoNewTabAction(url=url):
                new_page = await self.window.page.context.new_page()
                self.window.page = new_page
                _ = await new_page.goto(url)
            case SwitchTabAction(tab_index=tab_index):
                await self.switch_tab(tab_index)
            case WaitAction(time_ms=time_ms):
                await self.window.page.wait_for_timeout(time_ms)
            case GoBackAction():
                _ = await self.window.page.go_back()
            case GoForwardAction():
                _ = await self.window.page.go_forward()
            case ReloadAction():
                _ = await self.window.page.reload()
                await self.window.long_wait()
            case PressKeyAction(key=key):
                await self.window.page.keyboard.press(key)
            case ScrollUpAction(amount=amount):
                if amount is not None:
                    await self.window.page.mouse.wheel(delta_x=0, delta_y=-amount)
                else:
                    await self.window.page.keyboard.press("PageUp")
            case ScrollDownAction(amount=amount):
                if amount is not None:
                    await self.window.page.mouse.wheel(delta_x=0, delta_y=amount)
                else:
                    await self.window.page.keyboard.press("PageDown")
            case ScrapeAction():
                raise NotImplementedError("Scrape action is not supported in the browser controller")
            case _:
                raise ValueError(f"Unsupported action type: {type(action)}")

        # perform snapshot in execute
        return None

    async def execute_interaction_action(self, action: InteractionAction) -> BrowserSnapshot | None:
        if action.selector is None:
            raise ValueError(f"Selector is required for {action.name()}")
        press_enter = False
        if action.press_enter is not None:
            press_enter = action.press_enter
        # locate element (possibly in iframe)
        locator: Locator = await locale_element(self.window.page, action.selector)
        original_url = self.window.page.url

        action_timeout = self.window.config.wait.action_timeout

        match action:
            # Interaction actions
            case ClickAction():
                await locator.click(timeout=action_timeout)
            case FillAction(value=value):
                if text_contains_tabs(text=value):
                    if self.verbose:
                        logger.info(
                            "🪦 Indentation detected in fill action: simulating clipboard copy/paste for better string formatting"
                        )
                    await locator.focus()

                    if action.clear_before_fill:
                        await self.window.page.keyboard.press(key=f"{platform_control_key()}+A")
                        await self.window.short_wait()
                        await self.window.page.keyboard.press(key="Backspace")
                        await self.window.short_wait()

                    # Use isolated clipboard variable instead of system clipboard
                    await self.window.page.evaluate(
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

                    await self.window.short_wait()
                else:
                    await locator.fill(value, timeout=action_timeout, force=action.clear_before_fill)
                    await self.window.short_wait()
            case CheckAction(value=value):
                if value:
                    await locator.check()
                else:
                    await locator.uncheck()
            case SelectDropdownOptionAction(value=value, option_selector=option_selector):
                # Check if it's a standard HTML select
                tag_name: str = await locator.evaluate("el => el.tagName.toLowerCase()")
                if tag_name == "select":
                    # Handle standard HTML select
                    _ = await locator.select_option(value)
                elif option_selector is None:
                    raise ValueError(f"Option selector is required for {action.name()}")
                else:
                    option_locator = await locale_element(self.window.page, option_selector)
                    # Handle non-standard select
                    await option_locator.click()

            case ListDropdownOptionsAction():
                options = await dropdown_menu_options(self.window.page, action.selector.xpath_selector)
                if self.verbose:
                    logger.info(f"Dropdown options: {options}")
                raise NotImplementedError("ListDropdownOptionsAction is not supported in the browser controller")
            case _:
                raise ValueError(f"Unsupported action type: {type(action)}")
        if press_enter:
            if self.verbose:
                logger.info(f"🪦 Pressing enter for action {action.id}")
            await self.window.short_wait()
            await self.window.page.keyboard.press("Enter")
        if original_url != self.window.page.url:
            if self.verbose:
                logger.info(f"🪦 Page navigation detected for action {action.id} waiting for networkidle")
            await self.window.long_wait()

        # perform snapshot in execute
        return None

    async def execute(self, action: BaseAction) -> BrowserSnapshot:
        context = self.window.page.context
        num_pages = len(context.pages)
        match action:
            case InteractionAction():
                retval = await self.execute_interaction_action(action)
            case CompletionAction(success=success, answer=answer):
                snapshot = await self.window.snapshot()
                if self.verbose:
                    logger.info(
                        f"Completion action: status={'success' if success else 'failure'} with answer = {answer}"
                    )
                await self.window.close()
                return snapshot
            case _:
                retval = await self.execute_browser_action(action)
        # add short wait before we check for new tabs to make sure that
        # the page has time to be created
        await self.window.short_wait()
        if len(context.pages) != num_pages:
            if self.verbose:
                logger.info(f"🪦 Action {action.id} resulted in a new tab, switched to it...")
            await self.switch_tab(tab_index=-1)
        elif retval is not None:
            # only return snapshot if we didn't switch to a new tab
            # otherwise, the snapshot is out of date and we need to take a new one
            return retval

        return await self.window.snapshot()

    async def execute_multiple(self, actions: list[BaseAction]) -> list[BrowserSnapshot]:
        snapshots: list[BrowserSnapshot] = []
        for action in actions:
            snapshots.append(await self.execute(action))
        return snapshots
