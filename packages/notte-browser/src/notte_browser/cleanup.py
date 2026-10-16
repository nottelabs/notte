"""Bounded cleanup of owned browser resources."""

import asyncio
from collections.abc import Awaitable, Callable

from notte_core.logging import logger

RESOURCE_CLEANUP_TIMEOUT_SECONDS = 30


async def cleanup_resources(*cleanups: Callable[[], Awaitable[None]]) -> None:
    """Attempt every owned cleanup, with an independent deadline and safe logs."""
    cancelled: asyncio.CancelledError | None = None
    for cleanup in cleanups:
        try:
            async with asyncio.timeout(RESOURCE_CLEANUP_TIMEOUT_SECONDS):
                await cleanup()
        except asyncio.CancelledError as exc:
            cancelled = exc
        except Exception:
            logger.warning("Failed to release a browser resource")
    if cancelled is not None:
        raise cancelled
