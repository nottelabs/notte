import pytest
from loguru import logger

from notte.browser.driver import PlaywrightResource


def get_module_name(item: pytest.Item) -> str:
    return item.module.__name__ if item.module else "unknown_module"


_last_module = None


@pytest.hookimpl(trylast=True)
def pytest_runtest_teardown(item: pytest.Item):
    """Run cleanup after each module"""
    global _last_module
    current_module = get_module_name(item)

    # Only run cleanup when switching to a new module or at the last test
    if _last_module is not None and current_module != _last_module:
        import asyncio

        logger.info(f"Running browser pool cleanup at the end of module: {_last_module}")

        async def cleanup():
            await PlaywrightResource.browser_pool.cleanup(force=True)
            # await PlaywrightResource.browser_pool.stop()

        asyncio.run(cleanup())

    _last_module = current_module
