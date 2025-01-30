from playwright.async_api import Page
from typing_extensions import final

from notte.browser.driver import BrowserDriver
from notte.browser.snapshot import BrowserSnapshot
from notte.controller.actions import (
    BaseAction,
    CheckAction,
    ClickAction,
    FillAction,
    GoBackAction,
    GoForwardAction,
    GotoAction,
    PressKeyAction,
    ReloadAction,
    ScrapeAction,
    ScreenshotAction,
    ScrollDownAction,
    ScrollUpAction,
    SelectAction,
    TerminateAction,
    WaitAction,
)


@final
class BrowserController:
    def __init__(self, driver: BrowserDriver) -> None:
        self.driver: BrowserDriver = driver

    @property
    def page(self) -> Page:
        return self.driver.page

    async def execute(self, action: BaseAction) -> BrowserSnapshot:
        match action:
            case GotoAction(url=url):
                _ = await self.driver.goto(url)
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
                    await self.page.mouse.wheel(delta_x=0, delta_y=amount)
                else:
                    await self.page.keyboard.press("PageDown")
            case ScrollDownAction(amount=amount):
                if amount is not None:
                    await self.page.mouse.wheel(delta_x=0, delta_y=-amount)
                else:
                    await self.page.keyboard.press("PageUp")
            case ScreenshotAction():
                return await self.driver.snapshot(screenshot=True)
            case ScrapeAction():
                raise NotImplementedError("Scrape action is not supported in the browser controller")
            case TerminateAction():
                await self.driver.close()
            # Interaction actions
            case ClickAction(selector=selector):
                await self.page.click(selector)
            case FillAction(selector=selector, value=value):
                await self.page.fill(selector, value)
            case CheckAction(selector=selector, value=value):
                if value:
                    await self.page.check(selector)
                else:
                    await self.page.uncheck(selector)
            case SelectAction(selector=selector, value=value):
                _ = await self.page.select_option(selector, value)
            case _:
                raise ValueError(f"Unsupported action type: {type(action)}")
        await self.driver.short_wait()
        return await self.driver.snapshot()

    async def execute_multiple(self, actions: list[BaseAction]) -> list[BrowserSnapshot]:
        snapshots: list[BrowserSnapshot] = []
        for action in actions:
            snapshots.append(await self.execute(action))
        return snapshots
