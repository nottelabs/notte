# import pytest
# from loguru import logger

# from notte.browser.driver import PlaywrightResource


# def get_module_name(item: pytest.Item) -> str:
#     return item.module.__name__ if item.module else "unknown_module"


# _last_module = None


# @pytest.hookimpl(trylast=True)
# def pytest_runtest_teardown(item: pytest.Item):
#     """Run cleanup after each test and module"""
#     global _last_module
#     current_module = get_module_name(item)

#     import asyncio

#     # Run cleanup after each test
#     logger.info(f"Running browser pool cleanup after test: {item.name}")
#     asyncio.run(PlaywrightResource.browser_pool.cleanup(force=True))

#     # Additional cleanup when switching modules
#     if _last_module is not None and current_module != _last_module:
#         logger.info(f"Running browser pool cleanup and stop at the end of module: {_last_module}")

#         async def module_cleanup():
#             await PlaywrightResource.browser_pool.cleanup(force=True)
#             await PlaywrightResource.browser_pool.stop()

#         asyncio.run(module_cleanup())

#     _last_module = current_module
