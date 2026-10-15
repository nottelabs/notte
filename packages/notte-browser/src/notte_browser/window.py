import asyncio
import base64
import os
import random
import time
import traceback
from collections.abc import Awaitable
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable, ClassVar, Literal, Self

from notte_core.config import BrowserType, CookieDict, PlaywrightProxySettings, config
from notte_core.dom_tree import DomNode
from notte_core.errors import SnapshotProcessingError
from notte_core.logging import logger
from notte_core.profiling import profiler
from notte_core.raw_file import get_empty_dom_node, get_file_ext
from notte_core.snapshot import (
    BrowserSnapshot,
    SnapshotMetadata,
    TabsData,
    ViewportData,
)
from notte_core.types import (
    DEFAULT_HEADLESS_VIEWPORT_HEIGHT,
    DEFAULT_HEADLESS_VIEWPORT_WIDTH,
    AspectRatio,
    Cookie,
    LocalSessionStartRequest,
)
from notte_core.url import is_valid_url
from pydantic import BaseModel
from typing_extensions import override

from notte_browser.dom.parsing import parse_dom
from notte_browser.errors import (
    BrowserExpiredError,
    EmptyPageContentError,
    InvalidLocatorRuntimeError,
    InvalidProxyError,
    InvalidURLError,
    PageLoadingError,
    PlaywrightError,
    PlaywrightTimeoutError,
    UnexpectedBrowserError,
)
from notte_browser.js import script
from notte_browser.playwright_async_api import Browser, CDPSession, Locator, Page, Playwright, Response

_PAGE_METADATA = script("page_metadata.js")

WaitUntil = Literal["commit", "domcontentloaded", "load", "networkidle"]


class BrowserWindowOptions(BaseModel):
    headless: bool
    solve_captchas: bool
    user_agent: str | None
    proxy: PlaywrightProxySettings | None
    viewport_width: int | None
    viewport_height: int | None
    aspect_ratio: AspectRatio | None = None
    browser_type: BrowserType
    chrome_args: list[str] | None
    web_security: bool

    # Debugging args
    cdp_url: str | None
    debug_port: int | None
    custom_devtools_frontend: str | None

    extra_http_headers: dict[str, str] | None = None

    def set_cdp_url(self, cdp_url: str) -> Self:
        self.cdp_url = cdp_url
        return self

    @override
    def model_post_init(self, __context: Any) -> None:
        # Check that either both viewport options are set or neither
        if (self.viewport_width is None) != (self.viewport_height is None):
            raise ValueError("Both viewport_width and viewport_height must be set together or both must be None")

        if self.headless and self.viewport_width is None and self.viewport_height is None:
            if self.cdp_url is not None:
                logger.info(
                    "🪟 Headless CDP session detected. Leaving viewport unset so the remote browser geometry is preserved."
                )
                return

            if self.aspect_ratio is not None:
                self.viewport_width, self.viewport_height = self._fit_aspect_ratio_in_default_viewport(
                    self.aspect_ratio
                )
                message = (
                    f"🪟 Headless mode detected. Setting viewport to {self.viewport_width}x{self.viewport_height} "
                    + f"to respect aspect_ratio={self.aspect_ratio}."
                )
                logger.info(message)
                return

            width_variation = random.randint(-50, 50)
            height_variation = random.randint(-50, 50)
            logger.warning(
                f"🪟 Headless mode detected. Setting default viewport width and height to {DEFAULT_HEADLESS_VIEWPORT_WIDTH}x{DEFAULT_HEADLESS_VIEWPORT_HEIGHT} to avoid issues."
            )
            self.viewport_width = DEFAULT_HEADLESS_VIEWPORT_WIDTH + width_variation
            self.viewport_height = DEFAULT_HEADLESS_VIEWPORT_HEIGHT + height_variation

    @staticmethod
    def _fit_aspect_ratio_in_default_viewport(aspect_ratio: AspectRatio) -> tuple[int, int]:
        width_ratio, height_ratio = (int(part) for part in aspect_ratio.split(":"))
        return DEFAULT_HEADLESS_VIEWPORT_WIDTH, round(DEFAULT_HEADLESS_VIEWPORT_WIDTH * height_ratio / width_ratio)

    def get_chrome_args(self) -> list[str]:
        chrome_args = self.chrome_args or []
        if self.chrome_args is None:
            chrome_args.extend(
                [
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--no-zygote",
                    "--mute-audio",
                    '--js-flags="--max-old-space-size=100"',
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--start-maximized",
                ]
            )
        if os.getenv("DISABLE_GPU") is not None:
            logger.warning(
                "🪟 Disabling GPU in chrome args. You can remove the DISABLE_GPU environment variable to enable it."
            )
            chrome_args.extend(["--disable-gpu"])
        if len(chrome_args) == 0:
            logger.warning("Chrome args are empty. This is not recommended in production environments.")
        if not self.web_security:
            chrome_args.extend(
                [
                    "--disable-web-security",
                    "--disable-site-isolation-trials",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--remote-allow-origins=*",
                ]
            )

        if self.custom_devtools_frontend is not None:
            chrome_args.extend(
                [
                    f"--custom-devtools-frontend={self.custom_devtools_frontend}",
                ]
            )
        if self.debug_port is not None:
            chrome_args.append(f"--remote-debugging-port={self.debug_port}")
        return chrome_args

    @staticmethod
    def from_request(request: LocalSessionStartRequest) -> "BrowserWindowOptions":
        return BrowserWindowOptions(
            headless=request.headless,
            solve_captchas=request.solve_captchas,
            user_agent=request.user_agent,
            proxy=request.playwright_proxy,
            browser_type=request.browser_type,
            chrome_args=request.chrome_args,
            viewport_height=request.viewport_height,
            viewport_width=request.viewport_width,
            aspect_ratio=request.aspect_ratio,
            cdp_url=request.cdp_url,
            web_security=config.web_security,
            debug_port=config.debug_port,
            custom_devtools_frontend=config.custom_devtools_frontend,
            extra_http_headers=request.extra_http_headers,
        )


class ScreenshotMask:
    async def mask(self, page: Page) -> list[Locator]:  # pyright: ignore[reportUnusedParameter]
        return []


class BrowserWindow:
    """Active page and browser operations; caller-supplied pages are borrowed.

    launch/connect attach their owned transport to this window's close boundary.
    Options remain validated data, while live Playwright handles are ordinary state.
    """

    def __init__(
        self,
        page: Page,
        options: BrowserWindowOptions,
        *,
        on_close: Callable[[], Awaitable[None]] | None = None,
        screenshot_mask: ScreenshotMask | None = None,
    ) -> None:
        self._page: Page = page
        self.options: BrowserWindowOptions = options
        self.screenshot_mask: ScreenshotMask | None = screenshot_mask
        self.on_close: Callable[[], Awaitable[None]] | None = on_close
        self.page_callbacks: dict[str, Callable[[Page], None]] = {}
        self.goto_response: Response | None = None
        self._cdp_sessions: dict[int, CDPSession] = {}
        self._owned_browser: Browser | None = None
        self._owned_driver: Playwright | None = None
        page.set_default_timeout(config.timeout_default_ms)
        # Only final main-document responses establish navigation/raw-file state.
        self.page_callbacks["response"] = self._record_navigation_response  # pyright: ignore[reportArgumentType]
        self.apply_page_callbacks()

    async def _close_owned(self) -> None:
        try:
            async with asyncio.timeout(30):
                try:
                    if self._owned_browser is not None:
                        await self._owned_browser.close()
                finally:
                    if self._owned_driver is not None:
                        await self._owned_driver.stop()
        except Exception as e:
            logger.error(f"Failed to close window: {e}")
        finally:
            self._owned_browser = None
            self._owned_driver = None

    def _is_final_main_document_response(self, response: Response) -> bool:
        request = response.request
        is_redirect = response.status in {
            HTTPStatus.MOVED_PERMANENTLY,
            HTTPStatus.FOUND,
            HTTPStatus.SEE_OTHER,
            HTTPStatus.TEMPORARY_REDIRECT,
            HTTPStatus.PERMANENT_REDIRECT,
        }
        return request.is_navigation_request() and request.frame == self.page.main_frame and not is_redirect

    def _record_navigation_response(self, response: Response) -> None:
        if self._is_final_main_document_response(response):
            self.goto_response = response

    def apply_page_callbacks(self):
        for key, callback in self.page_callbacks.items():
            self.page.on(key, callback)  # pyright: ignore [reportArgumentType, reportCallIssue]

    @property
    def page(self) -> Page:
        if self._page.url != "about:blank" and self._page.is_closed() and len(self._page.context.pages) > 0:
            # reset to the last created page
            self.page = self._page.context.pages[-1]
        return self._page

    @property
    def tabs(self) -> list[Page]:
        return self._page.context.pages

    async def close(self) -> None:
        if self.on_close is not None:
            await self.on_close()
        await self._close_all_cdp_sessions()

    @page.setter
    def page(self, page: Page) -> None:
        # Drop the displaced page's cached CDP session so it doesn't linger until
        # window close. The on-close handler on the new page will handle eviction
        # when it closes; the previous page may still be alive but no longer
        # referenced by this window.
        _ = self._cdp_sessions.pop(id(self._page), None)
        self._page = page
        self.apply_page_callbacks()

    async def switch_tab(self, tab_index: int, *, verbose: bool = False) -> None:
        context = self.page.context
        if tab_index != -1 and (tab_index < 0 or tab_index >= len(context.pages)):
            raise ValueError(f"Tab index '{tab_index}' is out of range for context with {len(context.pages)} pages")
        tab_page = context.pages[tab_index]
        await tab_page.bring_to_front()
        self.page = tab_page
        await self.long_wait()
        if verbose:
            logger.info(
                f"🪦 Switched to tab {tab_index} with url: {tab_page.url} ({len(context.pages)} tabs in context)"
            )

    @property
    def is_chromium_based(self) -> bool:
        """Check if the browser is Chromium-based (supports CDP)."""
        return self.options.browser_type != "firefox"

    async def get_cdp_session(self, tab_idx: int | None = None) -> CDPSession:
        cdp_page = self.tabs[tab_idx] if tab_idx is not None else self.page
        key = id(cdp_page)
        cached = self._cdp_sessions.get(key)
        if cached is not None:
            return cached
        session = await cdp_page.context.new_cdp_session(cdp_page)
        self._cdp_sessions[key] = session

        # Prune on close so a later Page object reusing the same id() cannot
        # inherit a stale, already-detached session from the dict.
        def _drop_on_close(_page: Page) -> None:
            _ = self._cdp_sessions.pop(key, None)

        cdp_page.on("close", _drop_on_close)
        return session

    def _invalidate_cdp_session(self, tab_idx: int | None = None) -> None:
        cdp_page = self.tabs[tab_idx] if tab_idx is not None else self.page
        _ = self._cdp_sessions.pop(id(cdp_page), None)

    async def _close_all_cdp_sessions(self) -> None:
        sessions = list(self._cdp_sessions.values())
        self._cdp_sessions.clear()
        for session in sessions:
            try:
                _ = await asyncio.wait_for(session.detach(), timeout=2.0)
            except Exception as e:  # noqa: BLE001 - best-effort cleanup on shutdown
                logger.debug(f"CDP session detach failed during close: {type(e).__name__}: {e}")

    @profiler.profiled()
    async def long_wait(self) -> None:
        start_time = time.time()
        try:
            await self.page.wait_for_load_state("networkidle", timeout=config.timeout_goto_ms)
        except PlaywrightTimeoutError:
            if config.verbose:
                logger.warning(f"Timeout while waiting for networkidle state for '{self.page.url}'")
        await self.short_wait()
        # await self.page.wait_for_timeout(self._playwright.config.step_timeout)
        if config.verbose:
            logger.trace(f"Waited for networkidle state for '{self.page.url}' in {time.time() - start_time:.2f}s")

    @profiler.profiled()
    async def short_wait(self) -> None:
        await self.page.wait_for_timeout(config.wait_short_ms)

    async def tab_metadata(self, tab_idx: int | None = None) -> TabsData:
        page = self.tabs[tab_idx] if tab_idx is not None else self.page
        try:
            page_title = await asyncio.wait_for(page.title(), timeout=5.0)
        except PlaywrightError:
            page_title = page.url
        except TimeoutError:
            page_title = page.url

        return TabsData(
            tab_id=tab_idx if tab_idx is not None else -1,
            title=page_title,
            url=page.url,
        )

    @profiler.profiled(service_name="observation")
    async def snapshot_metadata(self) -> SnapshotMetadata:
        page = self.page
        # Read the active document in one browser call. Keep int() on the Python
        # side so fractional scroll offsets retain the existing truncation.
        metadata = await page.evaluate(_PAGE_METADATA)
        return SnapshotMetadata(
            title=metadata["title"],
            url=page.url,
            viewport=ViewportData(
                scroll_x=int(metadata["scroll_x"]),
                scroll_y=int(metadata["scroll_y"]),
                viewport_width=int(metadata["viewport_width"]),
                viewport_height=int(metadata["viewport_height"]),
                total_width=int(metadata["total_width"]),
                total_height=int(metadata["total_height"]),
            ),
            tabs=[
                TabsData(tab_id=i, title=metadata["title"], url=page.url) if tab is page else await self.tab_metadata(i)
                for i, tab in enumerate(self.tabs)
            ],
        )

    # Per-attempt timeout for a single CDP screenshot (attach + capture + detach).
    # Bounds hangs so the retry loop can actually retry instead of blocking on a stuck session.
    CDP_SCREENSHOT_TIMEOUT_S: ClassVar[float] = 10.0
    CDP_SCREENSHOT_MAX_ATTEMPTS: ClassVar[int] = 3

    @profiler.profiled(service_name="observation")
    async def _cdp_screenshot(self) -> bytes:
        """Take a screenshot using CDP protocol (faster than Playwright, but no mask support).

        The CDP session is cached on the window and reused across calls; it survives
        navigations on the same Page target. On any error the cached session is dropped
        so the outer retry loop in `screenshot()` gets a fresh one.
        """

        async def _run() -> bytes:
            cdp_session = await self.get_cdp_session()
            try:
                t_send = time.monotonic()
                result: dict[str, Any] = await cdp_session.send(  # pyright: ignore [reportUnknownMemberType]
                    "Page.captureScreenshot",
                    {"format": "jpeg", "quality": 85},
                )
                send_ms = (time.monotonic() - t_send) * 1000
                data = base64.b64decode(result["data"])
                logger.trace(f"CDP screenshot for {self.page.url}: send={send_ms:.0f}ms size={len(data)}B")
                return data
            except BaseException:
                # Must be BaseException, not Exception: asyncio.wait_for on timeout
                # raises CancelledError (BaseException since 3.8) and we'd otherwise
                # leave a stale session in the cache.
                self._invalidate_cdp_session()
                raise

        return await asyncio.wait_for(_run(), timeout=self.CDP_SCREENSHOT_TIMEOUT_S)

    @profiler.profiled(service_name="observation")
    async def screenshot(self, retries: int = config.empty_page_max_retry, *, _skip_cdp: bool = False) -> bytes:
        if retries <= 0:
            raise EmptyPageContentError(url=self.page.url, nb_retries=config.empty_page_max_retry)
        cdp_exhausted = _skip_cdp
        try:
            # Use CDP screenshot when no mask is needed and browser supports CDP (faster)
            if not _skip_cdp and self.screenshot_mask is None and self.is_chromium_based:
                cdp_start = time.monotonic()
                for attempt in range(1, self.CDP_SCREENSHOT_MAX_ATTEMPTS + 1):
                    attempt_start = time.monotonic()
                    try:
                        return await self._cdp_screenshot()
                    except asyncio.CancelledError:
                        raise
                    except asyncio.TimeoutError:
                        attempt_ms = (time.monotonic() - attempt_start) * 1000
                        logger.warning(
                            f"CDP screenshot timed out after {attempt_ms:.0f}ms for {self.page.url} (attempt {attempt}/{self.CDP_SCREENSHOT_MAX_ATTEMPTS}, budget={self.CDP_SCREENSHOT_TIMEOUT_S}s)"
                        )
                    except Exception as e:
                        attempt_ms = (time.monotonic() - attempt_start) * 1000
                        logger.opt(exception=True).warning(
                            f"CDP screenshot failed after {attempt_ms:.0f}ms for {self.page.url} (attempt {attempt}/{self.CDP_SCREENSHOT_MAX_ATTEMPTS}): {type(e).__name__}: {e}"
                        )
                    if attempt < self.CDP_SCREENSHOT_MAX_ATTEMPTS:
                        await self.short_wait()
                total_ms = (time.monotonic() - cdp_start) * 1000
                logger.warning(
                    f"CDP screenshot exhausted {self.CDP_SCREENSHOT_MAX_ATTEMPTS} attempts ({total_ms:.0f}ms total) for {self.page.url}, falling back to Playwright"
                )
                cdp_exhausted = True

            # Fall back to Playwright screenshot when mask is needed, CDP failed, or browser doesn't support CDP
            # Retry up to 2 times - DOM may change between mask creation and screenshot
            last_error: Exception | None = None
            for pw_attempt in range(1, 4):
                pw_start = time.monotonic()
                try:
                    t_mask = time.monotonic()
                    mask = await self.screenshot_mask.mask(self.page) if self.screenshot_mask is not None else None
                    mask_ms = (time.monotonic() - t_mask) * 1000
                    t_shot = time.monotonic()
                    data = await self.page.screenshot(mask=mask, type="jpeg", quality=85)
                    shot_ms = (time.monotonic() - t_shot) * 1000
                    logger.trace(
                        f"Playwright screenshot for {self.page.url}: mask={mask_ms:.0f}ms shot={shot_ms:.0f}ms size={len(data)}B attempt={pw_attempt}"
                    )
                    return data
                except PlaywrightTimeoutError:
                    pw_ms = (time.monotonic() - pw_start) * 1000
                    logger.warning(
                        f"Playwright screenshot timed out after {pw_ms:.0f}ms for {self.page.url} (attempt {pw_attempt}/3)"
                    )
                    raise  # Let outer handler deal with timeouts
                except Exception as e:
                    pw_ms = (time.monotonic() - pw_start) * 1000
                    logger.opt(exception=True).warning(
                        f"Playwright screenshot failed after {pw_ms:.0f}ms for {self.page.url} (attempt {pw_attempt}/3): {type(e).__name__}: {e}"
                    )
                    last_error = e
            raise last_error  # type: ignore[misc]

        except PlaywrightTimeoutError:
            logger.warning(
                f"Playwright screenshot timeout for {self.page.url}, retrying (remaining outer retries: {retries - 1})"
            )
            await self.short_wait()
            # Skip CDP on recursion if already exhausted — otherwise up to 30s of CDP retries
            # compound on every outer retry (5 × 30s = 150s worst case).
            return await self.screenshot(retries=retries - 1, _skip_cdp=cdp_exhausted)

    @profiler.profiled(service_name="observation")
    async def snapshot(
        self,
        screenshot: bool = True,
        retries: int = config.empty_page_max_retry,
        selector: str | None = None,
        skip_dom: bool = False,
    ) -> BrowserSnapshot:
        if retries <= 0:
            raise EmptyPageContentError(url=self.page.url, nb_retries=config.empty_page_max_retry)
        html_content: str = ""
        dom_node: DomNode | None = None
        snapshot_screenshot = None
        try:
            if selector:
                locator = self.page.locator(selector)
                html_content_await = profiler.profiled(service_name="observation")(locator.inner_html)()
            else:
                html_content_await = profiler.profiled(service_name="observation")(self.page.content)()

            html_content = await html_content_await
            if screenshot:
                snapshot_screenshot = await self.screenshot()
            if skip_dom:
                dom_node = DomNode.empty_root()
            else:
                dom_node = await parse_dom(self.page)

        except SnapshotProcessingError:
            await self.long_wait()
            return await self.snapshot(screenshot=screenshot, retries=retries - 1, selector=selector, skip_dom=skip_dom)

        except Exception as e:
            if "has been closed" in str(e):
                raise BrowserExpiredError() from e
            if "Unable to retrieve content because the page is navigating and changing the content" in str(e):
                # Should retry after the page is loaded
                await self.short_wait()
            elif "strict mode violation" in str(e):
                # Extract selector from the error or use the one provided
                selector_str = selector if selector else "unknown"
                raise InvalidLocatorRuntimeError(
                    message=f"Multiple elements found matching the selector. {str(e)}", selector=selector_str
                ) from e
            elif "Locator." in str(e) and ("Timeout" in str(e) or "waiting for locator" in str(e)):
                # Timeout error when waiting for a locator (element not found/visible)
                selector_str = selector if selector else "unknown"
                raise InvalidLocatorRuntimeError(
                    message=f"Element not found or not visible within timeout. {str(e)}", selector=selector_str
                ) from e
            else:
                raise UnexpectedBrowserError(url=self.page.url) from e

        if dom_node is None or (screenshot and snapshot_screenshot is None):
            if config.verbose:
                logger.warning(f"Empty page content for {self.page.url}. Retry in {config.wait_retry_snapshot_ms}ms")
            await self.page.wait_for_timeout(config.wait_retry_snapshot_ms)
            return await self.snapshot(screenshot=screenshot, retries=retries - 1, selector=selector, skip_dom=skip_dom)

        try:
            snapshot_metadata = await self.snapshot_metadata()

            from notte_browser.files import is_raw_file

            if is_raw_file(self):
                ext = get_file_ext(
                    headers=self.goto_response.headers if self.goto_response is not None else None, url=self.page.url
                )
                download_el = get_empty_dom_node(
                    id="I0",
                    text=f"Download entire page as raw {ext or ''} file. Use download_file, not click.",
                )
                dom_node.children.insert(0, download_el)
                download_el.set_parent(dom_node)

            return BrowserSnapshot(
                metadata=snapshot_metadata,
                html_content=html_content,
                dom_node=dom_node,
                screenshot=snapshot_screenshot,
            )
        except PlaywrightError:
            return await self.snapshot(screenshot=screenshot, retries=retries - 1, selector=selector, skip_dom=skip_dom)

    async def goto_and_wait(
        self,
        url: str | None = None,
        tries: int = 3,
        operation: Literal["back", "forward"] | None = None,
        wait_until: WaitUntil | None = None,
    ) -> None:
        def is_default_page():
            return self.page.url == "about:blank" and not url == "about:blank"

        while True:
            self.goto_response = None
            response: Response | None = None
            tries -= 1
            navigation_start = time.monotonic()

            try:
                # Waiting for commit makes Playwright return the response for this
                # exact navigation while still failing if the main document never
                # receives response headers. Later load states remain best-effort.
                match operation:
                    case None:
                        assert url is not None, "URL is required for goto"
                        response = await self.page.goto(
                            url,
                            timeout=config.timeout_goto_ms,
                            wait_until="commit",
                        )
                    case "back":
                        response = await self.page.go_back(
                            timeout=config.timeout_goto_ms,
                            wait_until="commit",
                        )
                    case "forward":
                        response = await self.page.go_forward(
                            timeout=config.timeout_goto_ms,
                            wait_until="commit",
                        )
                if response is not None:
                    self.goto_response = response
                    if response.status == HTTPStatus.PROXY_AUTHENTICATION_REQUIRED:
                        raise InvalidProxyError(url=url or self.page.url)
                    logger.info(f"Goto for {url=} committed with HTTP {response.status}: {response.status_text}")
            except PlaywrightTimeoutError as e:
                logger.warning(f"Goto for {url=} timed out before the main document committed")
                raise PageLoadingError(url=url or self.page.url) from e
            except InvalidProxyError:
                raise
            except Exception as e:
                if response is not None:
                    # Preserve the existing retry behavior for failures that occur
                    # after a successful main-document response.
                    if response.status == HTTPStatus.OK and tries > 0:
                        continue
                    logger.error(
                        f"Goto for {url=} failed with HTTP {response.status}: {response.status_text}, {traceback.format_exc()}"
                    )
                raise PageLoadingError(url=url or self.page.url) from e

            # Preserve the caller's requested load event and the existing total
            # navigation budget. A committed document can be used best-effort if
            # its later load events stall; a missing commit is an error above.
            if wait_until != "commit":
                remaining_ms = max(1, config.timeout_goto_ms - (time.monotonic() - navigation_start) * 1000)
                try:
                    await self.page.wait_for_load_state(wait_until or "load", timeout=remaining_ms)
                except PlaywrightTimeoutError:
                    logger.warning(
                        f"Goto for {url=} committed but timed out waiting for {wait_until or 'load'}; "
                        + "continuing with the loaded document"
                    )

            # Early load events deliberately skip the animation settle wait.
            if wait_until not in ("commit", "domcontentloaded"):
                await self.short_wait()

            if not is_default_page() or tries < 0:
                break

        if is_default_page():
            raise PageLoadingError(url=url or self.page.url)

    async def goto(self, url: str, tries: int = 3, wait_until: WaitUntil | None = None) -> None:
        if url == self.page.url:
            return
        prefixes = ("http://", "https://")

        if not any(url.startswith(prefix) for prefix in prefixes):
            logger.info(f"Provided URL doesnt have a scheme, adding https to {url}")
            url = "https://" + url

        if not is_valid_url(url, check_reachability=False):
            raise InvalidURLError(url=url)

        await self.goto_and_wait(url=url, tries=tries, operation=None, wait_until=wait_until)

    async def set_cookies(self, cookies: list[CookieDict] | None = None, cookie_path: str | Path | None = None) -> None:
        if cookies is None and cookie_path is not None:
            _cookies = Cookie.from_json(cookie_path)
            cookies = [cookie.model_dump() for cookie in _cookies]  # type: ignore
        if cookies is None:
            raise ValueError("No cookies provided")

        # Filter cookies to only include valid Playwright SetCookieParam fields with non-None values.
        # Playwright's add_cookies rejects extra fields (e.g., expirationDate, hostOnly, session, storeId)
        # and fields with None values (e.g., "partitionKey: expected string, got object").
        # Keep domain exactly as provided - don't modify it (host-only vs domain cookie semantics matter).
        # See: patchright/_impl/_api_structures.py SetCookieParam for the full list of valid fields.
        PLAYWRIGHT_COOKIE_FIELDS = {
            "name",
            "value",
            "url",
            "domain",
            "path",
            "expires",
            "httpOnly",
            "secure",
            "sameSite",
            "partitionKey",
        }
        filtered_cookies = [
            {k: v for k, v in cookie.items() if v is not None and k in PLAYWRIGHT_COOKIE_FIELDS} for cookie in cookies
        ]

        if config.verbose:
            logger.info("🍪 Adding cookies to browser...")
        await self.page.context.add_cookies(filtered_cookies)  # type: ignore

    async def get_cookies(self) -> list[CookieDict]:
        def format_cookie(data: dict[str, Any]) -> CookieDict:
            cookie = Cookie.model_validate(data)
            return CookieDict(
                name=cookie.name,
                domain=cookie.domain,
                path=cookie.path,
                httpOnly=cookie.httpOnly,
                expirationDate=cookie.expirationDate,
                hostOnly=cookie.hostOnly,
                sameSite=cookie.sameSite,
                secure=cookie.secure,
                session=cookie.session,
                storeId=cookie.storeId,
                value=cookie.value,
                expires=cookie.expires,
                partitionKey=cookie.partitionKey,
            )

        return [format_cookie(cookie) for cookie in await self.page.context.cookies()]  # type: ignore
