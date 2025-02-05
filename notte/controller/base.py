from loguru import logger
from playwright.async_api import Page
from typing_extensions import final

from notte.browser.driver import BrowserDriver
from notte.browser.snapshot import BrowserSnapshot
from notte.controller.actions import (
    BaseAction,
    CheckAction,
    ClickAction,
    CompletionAction,
    FillAction,
    GoBackAction,
    GoForwardAction,
    GotoAction,
    InteractionAction,
    ListDropdownOptionsAction,
    PressKeyAction,
    ReloadAction,
    ScrapeAction,
    ScrollDownAction,
    ScrollUpAction,
    SelectDropdownOptionAction,
    WaitAction,
)
from notte.pipe.preprocessing.dom.dropdown_menu import dropdown_menu_options
from notte.pipe.preprocessing.dom.locate import locale_element


@final
class BrowserController:
    def __init__(self, driver: BrowserDriver) -> None:
        self.driver: BrowserDriver = driver

    @property
    def page(self) -> Page:
        return self.driver.page

    async def execute_browser_action(self, action: BaseAction) -> BrowserSnapshot:
        match action:
            case GotoAction(url=url):
                return await self.driver.goto(url)
            case WaitAction(time_ms=time_ms):
                await self.page.wait_for_timeout(time_ms)
            case GoBackAction():
                _ = await self.page.go_back()
            case GoForwardAction():
                _ = await self.page.go_forward()
            case ReloadAction():
                _ = await self.page.reload()
                await self.driver.long_wait()
            case PressKeyAction(key=key):
                await self.page.keyboard.press(key)
            case ScrollUpAction(amount=amount):
                if amount is not None:
                    await self.page.mouse.wheel(delta_x=0, delta_y=-amount)
                else:
                    await self.page.keyboard.press("PageUp")
            case ScrollDownAction(amount=amount):
                if amount is not None:
                    await self.page.mouse.wheel(delta_x=0, delta_y=amount)
                else:
                    await self.page.keyboard.press("PageDown")
            # case ScreenshotAction():
            #     return await self.driver.snapshot(screenshot=True)
            case ScrapeAction():
                raise NotImplementedError("Scrape action is not supported in the browser controller")
            case CompletionAction(success=success, answer=answer):
                logger.info(f"Completion action: status={'success' if success else 'failure'} with answer = {answer}")
                await self.driver.close()
            case _:
                raise ValueError(f"Unsupported action type: {type(action)}")
        await self.driver.short_wait()
        return await self.driver.snapshot()

    async def execute_interaction_action(self, action: InteractionAction) -> BrowserSnapshot:
        if action.selector is None:
            raise ValueError(f"Selector is required for {action.name()}")
        press_enter = False
        if action.press_enter is not None:
            press_enter = action.press_enter
        # locate element (possibly in iframe)
        locator = await locale_element(self.page, action.selector)
        original_url = self.page.url
        match action:
            # Interaction actions
            case ClickAction():
                await locator.click()
            case FillAction(value=value):
                await locator.fill(value)
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
                    option_locator = await locale_element(self.page, option_selector)
                    # Handle non-standard select
                    await option_locator.click()

            case ListDropdownOptionsAction():
                options = await dropdown_menu_options(self.page, action.selector.xpath_selector)
                logger.info(f"Dropdown options: {options}")
                raise NotImplementedError("ListDropdownOptionsAction is not supported in the browser controller")
            case _:
                raise ValueError(f"Unsupported action type: {type(action)}")
        if press_enter:
            logger.info(f"🪦 Pressing enter for action {action.id}")
            await self.driver.short_wait()
            await self.page.keyboard.press("Enter")
        if original_url != self.page.url:
            logger.info(f"🪦 Page navigation detected for action {action.id} waiting for networkidle")
            await self.driver.long_wait()
        await self.driver.short_wait()
        return await self.driver.snapshot()

    async def execute(self, action: BaseAction) -> BrowserSnapshot:
        if isinstance(action, InteractionAction):
            return await self.execute_interaction_action(action)
        else:
            return await self.execute_browser_action(action)

    async def execute_multiple(self, actions: list[BaseAction]) -> list[BrowserSnapshot]:
        snapshots: list[BrowserSnapshot] = []
        for action in actions:
            snapshots.append(await self.execute(action))
        return snapshots
