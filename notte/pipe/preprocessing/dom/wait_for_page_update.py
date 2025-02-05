# from collections.abc import AsyncGenerator, Awaitable
# from contextlib import asynccontextmanager
# import time
# from patchright.async_api import Page, TimeoutError as PlaywrightTimeoutError
# import asyncio
# from loguru import logger

# # @asynccontextmanager
# # async def wait_for_page_update_2(
# #     page: Page,
# #     timeout: int = 1000,
# #     wait_until: str = "domcontentloaded"
# # ) -> AsyncGenerator[None, None]:
# #     """Context manager that waits for navigation or response if they occur after an action.

# #     Args:
# #         page: Playwright page object
# #         timeout: Maximum time to wait in milliseconds
# #         wait_until: Navigation wait condition ('domcontentloaded', 'load', 'networkidle')

# #     Example:
# #         async with wait_for_page_update(page):
# #             success = await element.click()
# #     """
# #     try:
# #         navigation_task = None
# #         response_task = None

# #         async with page.expect_navigation(wait_until=wait_until, timeout=timeout) as navigation, \
# #                   page.expect_response("**/*", timeout=timeout) as response:

# #             yield

# #             try:
# #                 # Create tasks but don't await them yet
# #                 navigation_task = asyncio.create_task(navigation.value)
# #                 response_task = asyncio.create_task(response.value)

# #                 # Wait for first completion
# #                 _, pending = await asyncio.wait(
# #                     [navigation_task, response_task],
# #                     return_when=asyncio.FIRST_COMPLETED
# #                 )

# #                 # Properly cancel pending tasks
# #                 for task in pending:
# #                     _ = task.cancel()
# #                     try:
# #                         await task
# #                     except asyncio.CancelledError:
# #                         pass

# #                 # Wait for network to be idle
# #                 try:
# #                     await page.wait_for_load_state("networkidle", timeout=timeout)
# #                 except PlaywrightTimeoutError:
# #                     logger.debug("Network did not reach idle state within timeout")

# #             except Exception as e:
# #                 logger.error(f"Error waiting for navigation/response: {e}")
# #                 raise
# #             finally:
# #                 # Clean up tasks if they weren't handled
# #                 if navigation_task and not navigation_task.done():
# #                     navigation_task.cancel()
# #                 if response_task and not response_task.done():
# #                     response_task.cancel()

# #     except PlaywrightTimeoutError:
# #         logger.debug("No navigation or response detected within timeout")
# #     except Exception as e:
# #         logger.error(f"Unexpected error in wait_for_page_update: {e}")
# #         raise


# @asynccontextmanager
# async def wait_for_page_update(
#     page: Page,
#     timeout: int = 500,
#     wait_until: str = "domcontentloaded"
# ) -> AsyncGenerator[None, None]:
#     """Context manager that waits for navigation or response if they occur after an action.

#     Args:
#         page: Playwright page object
#         timeout: Maximum time to wait in milliseconds
#         wait_until: Navigation wait condition ('domcontentloaded', 'load', 'networkidle')

#     Example:
#         async with wait_for_page_update(page):
#             success = await element.click()
#     """
#     try:
#         # Start listening but don't await yet
#         # event = 'popup'
#         page_promise: Awaitable[Page] = page.context.wait_for_event("page", timeout=timeout)
#         navigation_promise = page.wait_for_navigation(wait_until=wait_until, timeout=timeout)
#         response_promise = page.wait_for_response("**/*", timeout=timeout)

#         # Execute the action
#         yield
#         wait_time = time.time()
#         # Now check if a new page was created
#         try:
#             done, _ = await asyncio.wait(
#                 [
#                     asyncio.create_task(navigation_promise.value),
#                     asyncio.create_task(response_promise.value),
#                     asyncio.create_task(page_promise),
#                 ],
#                 timeout=timeout/1000,  # convert to seconds for asyncio.wait
#                 return_when=asyncio.FIRST_COMPLETED
#             )
#             if done:
#                 try:
#                     # Try less strict load states first
#                     await page.wait_for_load_state("networkidle", timeout=10000)
#                 except PlaywrightTimeoutError:
#                     logger.warning("Page didn't reach domcontentloaded state, continuing anyway")

#             # Store the page even if load state isn't complete
#             logger.info(f"Navitation event detected for {page.url}. Took {time.time() - wait_time} seconds.")
#             # self._pages.append(new_page)
#             # self._current_page_url = new_page.url
#         except PlaywrightTimeoutError:
#             # No new page was created, which is the common case
#             pass
#     except PlaywrightTimeoutError:
#         logger.debug("No navigation or response detected within timeout")
#     except Exception as e:
#         logger.error(f"Unexpected error in wait_for_page_update: {e}")
#         raise
