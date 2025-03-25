from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio

from notte.browser.pool.base import BaseBrowserPool, BrowserResource, BrowserResourceOptions
from notte.browser.pool.local_pool import LocalBrowserPool
from notte.browser.pool.ports import PortManager

# Add this configuration at the top of the file
pytestmark = pytest.mark.asyncio


@pytest.fixture
async def pool_generator():
    """Create a fresh pool for each test"""
    pool = LocalBrowserPool()
    try:
        await pool.start()
        yield pool
    finally:
        await pool.cleanup()
        await pool.stop()


@pytest_asyncio.fixture
async def pool(pool_generator: AsyncGenerator[BaseBrowserPool, None]) -> BaseBrowserPool:
    """Helper fixture that returns the NotteEnv instance directly"""
    return await anext(pool_generator)


@pytest.mark.asyncio
async def test_pool_initialization(pool: LocalBrowserPool):
    """Test initial pool state"""
    stats = pool.check_sessions()
    assert stats == {"open_browsers": 0, "open_contexts": 0}
    assert len(pool.available_browsers()) == 0


@pytest.mark.asyncio
async def test_resource_creation_and_tracking(pool: LocalBrowserPool):
    """Test creating resources and tracking their counts"""

    resources: list[BrowserResource] = []

    # Create resources one by one and verify counts
    for i in range(5):
        resource = await pool.get_browser_resource(BrowserResourceOptions(headless=True))
        resources.append(resource)

        stats = pool.check_sessions()
        assert stats["open_contexts"] == i + 1
        # Browser count should increase every 4 contexts (contexts_per_browser)
        assert stats["open_browsers"] == (i // 4) + 1


@pytest.mark.asyncio
async def test_resource_cleanup(pool: LocalBrowserPool):
    """Test cleaning up resources one by one"""

    # Create 6 resources
    resources = [await pool.get_browser_resource(BrowserResourceOptions(headless=True)) for _ in range(6)]

    initial_stats = pool.check_sessions()
    assert initial_stats["open_contexts"] == 6
    assert initial_stats["open_browsers"] == 2  # With 4 contexts per browser

    # Release resources one by one
    for i, resource in enumerate(resources):
        await pool.release_browser_resource(resource)
        stats = pool.check_sessions()
        assert stats["open_contexts"] == 5 - i
        # Browser count should decrease when all its contexts are closed
        remaining_contexts = 5 - i
        if remaining_contexts == 0:
            assert stats["open_browsers"] == 0, (
                f"Expected 0 open browsers for {remaining_contexts} contexts, got {stats['open_browsers']}"
            )
        else:
            assert stats["open_browsers"] in [
                1,
                2,
            ], f"Expected 1 or 2 open browsers for {remaining_contexts} contexts, got {stats['open_browsers']}"


@pytest.mark.asyncio
async def test_cleanup_with_exceptions(pool: LocalBrowserPool):
    """Test cleanup with different except_resources configurations"""

    # Create 8 resources
    resources = [await pool.get_browser_resource(BrowserResourceOptions(headless=True)) for _ in range(8)]

    # Test cleanup with no exceptions (should close everything)
    await pool.cleanup(except_resources=None)
    stats = pool.check_sessions()
    assert stats == {"open_browsers": 0, "open_contexts": 0}

    # Create new resources
    resources = [await pool.get_browser_resource(BrowserResourceOptions(headless=True)) for _ in range(8)]

    # Test cleanup with all resources excepted (should close nothing)
    await pool.cleanup(except_resources=resources)
    stats = pool.check_sessions()
    assert stats["open_contexts"] == 8
    assert stats["open_browsers"] == 2

    # Test cleanup with partial exceptions
    await pool.cleanup(except_resources=resources[:4])
    stats = pool.check_sessions()
    assert stats["open_contexts"] == 4
    assert stats["open_browsers"] == 1


@pytest.mark.asyncio
async def test_resource_creation_after_cleanup(pool: LocalBrowserPool):
    """Test that resources can be created after cleanup"""

    # Create and cleanup resources
    _ = [await pool.get_browser_resource(BrowserResourceOptions(headless=True)) for _ in range(4)]
    await pool.cleanup()

    # Verify cleanup
    stats = pool.check_sessions()
    assert stats == {"open_browsers": 0, "open_contexts": 0}

    # Create new resources
    new_resources = [await pool.get_browser_resource(BrowserResourceOptions(headless=True)) for _ in range(4)]
    stats = pool.check_sessions()
    assert stats["open_contexts"] == 4
    assert stats["open_browsers"] == 1

    await pool.cleanup(except_resources=new_resources)
    new_stats = pool.check_sessions()
    assert new_stats["open_contexts"] == 4
    assert new_stats["open_browsers"] == 1


@pytest.mark.asyncio
async def test_create_max_contexts_after_cleanup(pool: LocalBrowserPool):
    """Test that we can create max contexts after cleanup"""
    # simulate some resources being created and cleanup
    _ = [await pool.get_browser_resource(BrowserResourceOptions(headless=True)) for _ in range(4)]
    await pool.cleanup()
    assert pool.check_sessions()["open_contexts"] == 0

    # Try to create max contexts
    _ = [
        await pool.get_browser_resource(BrowserResourceOptions(headless=True))
        for _ in range(pool.local_config.get_max_contexts())
    ]
    assert pool.check_sessions()["open_contexts"] == pool.local_config.get_max_contexts()
    await pool.cleanup()
    assert pool.check_sessions()["open_contexts"] == 0


@pytest.mark.skip(reason="Skip on CICD because head mode is not supported")
@pytest.mark.asyncio
async def test_mixed_headless_modes(pool: LocalBrowserPool):
    """Test managing resources with different headless modes"""

    # Create mix of headless and non-headless resources
    _ = [await pool.get_browser_resource(BrowserResourceOptions(headless=True)) for _ in range(3)]
    _ = [await pool.get_browser_resource(BrowserResourceOptions(headless=False)) for _ in range(3)]

    stats = pool.check_sessions()
    assert stats["open_contexts"] == 6
    assert stats["open_browsers"] == 2

    # Verify browser tracking by headless mode
    assert len(pool.available_browsers(headless=True)) == 1
    assert len(pool.available_browsers(headless=False)) == 1

    await pool.cleanup()
    stats = pool.check_sessions()
    assert stats["open_contexts"] == 0
    assert stats["open_browsers"] == 0


@pytest.mark.asyncio
async def test_resource_limits(pool: LocalBrowserPool):
    """Test behavior when approaching resource limits"""

    max_contexts = pool.local_config.get_max_contexts()
    resources: list[BrowserResource] = []

    # Try to create more than max_contexts
    with pytest.raises(ValueError, match="Maximum number of browsers"):
        for _ in range(max_contexts + 1):
            resources.append(await pool.get_browser_resource(BrowserResourceOptions(headless=True)))

    # Verify we can still create resources after hitting the limit
    await pool.cleanup()
    new_resource = await pool.get_browser_resource(BrowserResourceOptions(headless=True))
    assert new_resource is not None

    await pool.cleanup()
    stats = pool.check_sessions()
    assert stats["open_contexts"] == 0
    assert stats["open_browsers"] == 0


@pytest.mark.asyncio
async def test_browser_reuse(pool: LocalBrowserPool):
    """Test that browsers are reused efficiently"""

    # Create 3 resources (should use single browser)
    resources = [await pool.get_browser_resource(BrowserResourceOptions(headless=True)) for _ in range(3)]
    stats = pool.check_sessions()
    assert stats["open_browsers"] == 1

    # Release middle resource
    await pool.release_browser_resource(resources[1])

    # Create new resource (should reuse existing browser)
    _ = await pool.get_browser_resource(BrowserResourceOptions(headless=True))
    stats = pool.check_sessions()
    assert stats["open_browsers"] == 1
    assert stats["open_contexts"] == 3


@pytest.mark.asyncio
async def test_error_handling(pool: LocalBrowserPool):
    """Test error handling scenarios"""

    # Try to release non-existent resource
    with pytest.raises(ValueError, match="Browser 'fake' not found in available browsers"):
        await pool.release_browser_resource(
            BrowserResource(page=None, browser_id="fake", context_id="fake", headless=True)  # type: ignore
        )

    # Create and release same resource twice
    resource = await pool.get_browser_resource(BrowserResourceOptions(headless=True))
    await pool.release_browser_resource(resource)
    with pytest.raises(ValueError, match="not found in available browsers "):
        await pool.release_browser_resource(resource)


@pytest.mark.asyncio
async def test_new_resource_with_port(pool: LocalBrowserPool):
    """Test that we can create max contexts after cleanup"""
    # simulate some resources being created and cleanup
    port = PortManager().acquire_port()
    resource = await pool.get_browser_resource(BrowserResourceOptions(headless=True, debug_port=port))
    assert resource.resource_options.debug_port == port

    await pool.cleanup()
    assert pool.check_sessions()["open_contexts"] == 0
