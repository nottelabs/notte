"""Visual effects for informative video replays.

This module provides visual feedback during action execution to make
video replays easier to understand. All effects are disabled by default
and can be enabled individually via config options.
"""

from typing import TypedDict

from notte_core.common.config import config
from notte_core.common.logging import logger

from notte_browser.playwright_async_api import Locator, Page


class BoundingBox(TypedDict):
    x: float
    y: float
    width: float
    height: float


# Lucide icon SVG paths (24x24 viewBox)
LUCIDE_ICONS: dict[str, str] = {
    # Click - mouse pointer
    "click": '<path d="M3 3l7.07 16.97 2.51-7.39 7.39-2.51L3 3z"/><path d="M13 13l6 6"/>',
    # Fill/Type - text cursor
    "fill": '<path d="M17 22h-1a4 4 0 0 1-4-4V6a4 4 0 0 1 4-4h1"/><path d="M7 22h1a4 4 0 0 0 4-4v-1"/><path d="M7 2h1a4 4 0 0 1 4 4v1"/>',
    # Scroll down
    "scroll_down": '<path d="M12 5v14"/><path d="m19 12-7 7-7-7"/>',
    # Scroll up
    "scroll_up": '<path d="M12 19V5"/><path d="m5 12 7-7 7 7"/>',
    # Select dropdown
    "select": '<path d="m6 9 6 6 6-6"/>',
    # Checkbox
    "check": '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="m9 12 2 2 4-4"/>',
    # Upload
    "upload": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" x2="12" y1="3" y2="15"/>',
    # Download
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/>',
    # Goto/Navigate - globe
    "goto": '<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/>',
    # New tab
    "new_tab": '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    # Back
    "back": '<path d="m12 19-7-7 7-7"/><path d="M19 12H5"/>',
    # Forward
    "forward": '<path d="m12 5 7 7-7 7"/><path d="M5 12h14"/>',
    # Reload
    "reload": '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
    # Keyboard/Press key
    "press": '<rect width="20" height="16" x="2" y="4" rx="2"/><path d="M6 8h.001"/><path d="M10 8h.001"/><path d="M14 8h.001"/><path d="M18 8h.001"/><path d="M8 12h.001"/><path d="M12 12h.001"/><path d="M16 12h.001"/><path d="M7 16h10"/>',
    # Wait/Clock
    "wait": '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    # Switch tab
    "switch_tab": '<rect width="8" height="8" x="2" y="2" rx="1"/><path d="M14 2c1 0 2 1 2 2v4c0 1-1 2-2 2"/><path d="M20 2c1 0 2 1 2 2v4c0 1-1 2-2 2"/><rect width="8" height="8" x="14" y="14" rx="1"/>',
    # Close
    "close": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    # Scrape/Extract
    "scrape": '<path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><line x1="16" x2="8" y1="13" y2="13"/><line x1="16" x2="8" y1="17" y2="17"/>',
    # Default/Activity
    "default": '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
}


def _get_icon_for_action(action_type: str) -> str:
    """Map action type to appropriate Lucide icon."""
    action_lower = action_type.lower()

    if "click" in action_lower:
        return LUCIDE_ICONS["click"]
    elif "fill" in action_lower or "type" in action_lower:
        return LUCIDE_ICONS["fill"]
    elif "scroll_down" in action_lower or "scrolldown" in action_lower:
        return LUCIDE_ICONS["scroll_down"]
    elif "scroll_up" in action_lower or "scrollup" in action_lower:
        return LUCIDE_ICONS["scroll_up"]
    elif "scroll" in action_lower:
        return LUCIDE_ICONS["scroll_down"]
    elif "select" in action_lower or "dropdown" in action_lower:
        return LUCIDE_ICONS["select"]
    elif "check" in action_lower:
        return LUCIDE_ICONS["check"]
    elif "upload" in action_lower:
        return LUCIDE_ICONS["upload"]
    elif "download" in action_lower:
        return LUCIDE_ICONS["download"]
    elif "new_tab" in action_lower or "newtab" in action_lower:
        return LUCIDE_ICONS["new_tab"]
    elif "goto" in action_lower or "navigate" in action_lower:
        return LUCIDE_ICONS["goto"]
    elif "back" in action_lower:
        return LUCIDE_ICONS["back"]
    elif "forward" in action_lower:
        return LUCIDE_ICONS["forward"]
    elif "reload" in action_lower or "refresh" in action_lower:
        return LUCIDE_ICONS["reload"]
    elif "press" in action_lower or "key" in action_lower:
        return LUCIDE_ICONS["press"]
    elif "wait" in action_lower:
        return LUCIDE_ICONS["wait"]
    elif "switch" in action_lower or "tab" in action_lower:
        return LUCIDE_ICONS["switch_tab"]
    elif "close" in action_lower:
        return LUCIDE_ICONS["close"]
    elif "scrape" in action_lower:
        return LUCIDE_ICONS["scrape"]
    else:
        return LUCIDE_ICONS["default"]


class ReplayEffects:
    """Visual effects for replay videos."""

    @staticmethod
    async def flash_element_highlight(locator: Locator, page: Page) -> None:
        """Flash a highlight border around an element before interaction.

        Creates a DOM overlay with a glowing border that fades out.
        Uses locator bounding box for accurate positioning.
        Only runs if replay_highlight_elements is enabled.
        """
        if not config.replay_highlight_elements:
            return

        try:
            bbox = await locator.bounding_box()
            if bbox is None:
                return
        except Exception as e:
            logger.debug(f"Failed to get bounding box for highlight: {e}")
            return

        duration_ms = config.replay_highlight_duration_ms
        color = config.replay_highlight_color

        js_code = f"""
        (bbox) => {{
            // Remove any existing highlight
            const existing = document.getElementById('notte-replay-highlight');
            if (existing) existing.remove();

            const overlay = document.createElement('div');
            overlay.id = 'notte-replay-highlight';
            overlay.style.cssText = `
                position: fixed;
                top: ${{bbox.y - 4}}px;
                left: ${{bbox.x - 4}}px;
                width: ${{bbox.width + 8}}px;
                height: ${{bbox.height + 8}}px;
                border: 3px solid {color};
                border-radius: 4px;
                box-shadow: 0 0 20px {color}, inset 0 0 10px {color}40;
                pointer-events: none;
                z-index: 2147483647;
                animation: notte-highlight-fade {duration_ms}ms ease-out forwards;
            `;

            // Add keyframes if not already present
            if (!document.getElementById('notte-replay-styles')) {{
                const style = document.createElement('style');
                style.id = 'notte-replay-styles';
                style.textContent = `
                    @keyframes notte-highlight-fade {{
                        0% {{ opacity: 1; transform: scale(1); }}
                        70% {{ opacity: 0.8; transform: scale(1.02); }}
                        100% {{ opacity: 0; transform: scale(1.05); }}
                    }}
                    @keyframes notte-icon-fade {{
                        0% {{ opacity: 0; transform: translate(-50%, -50%) scale(0.8); }}
                        10% {{ opacity: 1; transform: translate(-50%, -50%) scale(1); }}
                        80% {{ opacity: 1; transform: translate(-50%, -50%) scale(1); }}
                        100% {{ opacity: 0; transform: translate(-50%, -50%) scale(0.9); }}
                    }}
                `;
                document.head.appendChild(style);
            }}

            document.body.appendChild(overlay);

            // Auto-remove after animation
            setTimeout(() => overlay.remove(), {duration_ms});
            return true;
        }}
        """

        try:
            await page.evaluate(js_code, bbox)
            # Wait for highlight to be visible before proceeding
            await page.wait_for_timeout(min(duration_ms // 2, 400))
        except Exception as e:
            logger.debug(f"Failed to show element highlight: {e}")

    @staticmethod
    async def show_action_overlay(page: Page, action_type: str) -> None:
        """Display an action icon in the bottom right of the viewport.

        Shows a Lucide icon representing the action type (5% of min viewport dimension).
        Only runs if replay_action_overlay is enabled.
        """
        if not config.replay_action_overlay:
            return

        duration_ms = config.replay_action_overlay_duration_ms
        icon_path = _get_icon_for_action(action_type)

        js_code = f"""
        () => {{
            // Remove any existing overlay
            const existing = document.getElementById('notte-action-overlay');
            if (existing) existing.remove();

            // Calculate icon size as 5% of min(width, height)
            const size = Math.floor(Math.min(window.innerWidth, window.innerHeight) * 0.05);
            const minSize = 32;  // Minimum readable size
            const maxSize = 80;  // Maximum size
            const iconSize = Math.max(minSize, Math.min(maxSize, size));
            const padding = Math.floor(iconSize * 0.3);
            const containerSize = iconSize + padding * 2;

            const overlay = document.createElement('div');
            overlay.id = 'notte-action-overlay';
            overlay.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="${{iconSize}}" height="${{iconSize}}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    {icon_path}
                </svg>
            `;
            overlay.style.cssText = `
                position: fixed;
                bottom: 20px;
                right: 20px;
                width: ${{containerSize}}px;
                height: ${{containerSize}}px;
                background: rgba(0, 0, 0, 0.75);
                color: #fff;
                border-radius: 12px;
                display: flex;
                align-items: center;
                justify-content: center;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
                border: 1px solid rgba(255, 255, 255, 0.15);
                z-index: 2147483647;
                pointer-events: none;
                animation: notte-icon-fade {duration_ms}ms ease-out forwards;
            `;

            // Add keyframes if not already present
            if (!document.getElementById('notte-replay-styles')) {{
                const style = document.createElement('style');
                style.id = 'notte-replay-styles';
                style.textContent = `
                    @keyframes notte-highlight-fade {{
                        0% {{ opacity: 1; transform: scale(1); }}
                        70% {{ opacity: 0.8; transform: scale(1.02); }}
                        100% {{ opacity: 0; transform: scale(1.05); }}
                    }}
                    @keyframes notte-icon-fade {{
                        0% {{ opacity: 0; transform: scale(0.8); }}
                        10% {{ opacity: 1; transform: scale(1); }}
                        80% {{ opacity: 1; transform: scale(1); }}
                        100% {{ opacity: 0; transform: scale(0.9); }}
                    }}
                `;
                document.head.appendChild(style);
            }}

            document.body.appendChild(overlay);

            // Auto-remove after animation
            setTimeout(() => overlay.remove(), {duration_ms});
        }}
        """

        try:
            await page.evaluate(js_code)
        except Exception as e:
            logger.debug(f"Failed to show action overlay: {e}")

    @staticmethod
    async def smooth_scroll(page: Page, delta_y: int) -> None:
        """Animate scroll over a configurable duration.

        Uses requestAnimationFrame with easing for smooth visual effect.
        Only runs if replay_smooth_scroll is enabled.

        Returns True if smooth scroll was performed, False if caller should use default.
        """
        if not config.replay_smooth_scroll:
            return

        duration_ms = config.replay_scroll_duration_ms

        js_code = f"""
        (deltaY) => {{
            return new Promise((resolve) => {{
                const startY = window.scrollY;
                const startTime = performance.now();
                const duration = {duration_ms};

                // Easing function (ease-out cubic)
                const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3);

                function animate(currentTime) {{
                    const elapsed = currentTime - startTime;
                    const progress = Math.min(elapsed / duration, 1);
                    const eased = easeOutCubic(progress);

                    window.scrollTo(0, startY + (deltaY * eased));

                    if (progress < 1) {{
                        requestAnimationFrame(animate);
                    }} else {{
                        resolve(true);
                    }}
                }}

                requestAnimationFrame(animate);
            }});
        }}
        """

        try:
            await page.evaluate(js_code, delta_y)
        except Exception as e:
            logger.debug(f"Failed to perform smooth scroll: {e}")
            # Fallback to instant scroll
            await page.mouse.wheel(delta_x=0, delta_y=delta_y)

    @staticmethod
    async def cleanup_overlays(page: Page) -> None:
        """Remove any lingering replay overlay elements.

        Should be called before taking screenshots to ensure clean captures.
        """
        js_code = """
        () => {
            const ids = ['notte-replay-highlight', 'notte-action-overlay'];
            ids.forEach(id => {
                const el = document.getElementById(id);
                if (el) el.remove();
            });
        }
        """

        try:
            await page.evaluate(js_code)
        except Exception as e:
            logger.debug(f"Failed to cleanup overlays: {e}")

    @staticmethod
    def should_use_slow_typing() -> bool:
        """Check if slow typing mode is enabled."""
        return config.replay_slow_typing

    @staticmethod
    def get_typing_delay() -> int:
        """Get the delay between characters for slow typing."""
        return config.replay_typing_delay_ms
