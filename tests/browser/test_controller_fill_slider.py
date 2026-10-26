"""A fill on an ARIA slider (`role="slider"`) moves it to the value with its keyboard.

`locator.fill` rejects such an element (it is not an input), so no action could set a custom slider
(noUiSlider, MUI, Radix). The keys are the ones https://www.w3.org/WAI/ARIA/apg/patterns/slider/ defines.
"""

import json
from urllib.parse import quote

import pytest
from notte_browser.session import NotteSession
from notte_core.actions import FillAction

# A slider from 0 to 100 that moves by `step` with the arrows and by `page` with Page Up / Down (0: not
# handled), `delay` ms after the key (a slider that re-renders), with Left / Right swapped when `rtl`.
SLIDER = """<div id="slider" role="slider" tabindex="0" aria-label="Price" aria-valuemin="0" aria-valuemax="100"
aria-valuenow="20" style="width: 200px; height: 20px; background: #ccc"></div>
<script>
const {step, page, delay, rtl} = OPTIONS;
const slider = document.getElementById("slider");
const moves = {ArrowUp: step, ArrowDown: -step, ArrowRight: rtl ? -step : step, ArrowLeft: rtl ? step : -step,
    Home: -1000, End: 1000};
if (page) Object.assign(moves, {PageUp: page, PageDown: -page});
slider.addEventListener("keydown", (event) => {
    if (!(event.key in moves)) return;
    event.preventDefault();
    const value = Math.min(100, Math.max(0, Number(slider.getAttribute("aria-valuenow")) + moves[event.key]));
    setTimeout(() => slider.setAttribute("aria-valuenow", String(value)), delay);
});
</script>"""

CASES = {
    "page keys then arrows": ({"step": 1, "page": 10, "delay": 0, "rtl": False}, "47", "47"),
    "page keys past the value": ({"step": 5, "page": 30, "delay": 0, "rtl": False}, "65", "65"),
    "down to a lower value": ({"step": 5, "page": 30, "delay": 0, "rtl": False}, "5", "5"),
    "arrows only": ({"step": 5, "page": 0, "delay": 0, "rtl": False}, "60", "60"),
    "between two steps": ({"step": 10, "page": 0, "delay": 0, "rtl": False}, "42", "40"),
    "an end": ({"step": 10, "page": 0, "delay": 0, "rtl": False}, "100", "100"),
    "past an end": ({"step": 10, "page": 0, "delay": 0, "rtl": False}, "250", "100"),
    "right-to-left": ({"step": 10, "page": 0, "delay": 0, "rtl": True}, "50", "50"),
    "updated after the key": ({"step": 10, "page": 0, "delay": 30, "rtl": False}, "50", "50"),
    "a formatted number": ({"step": 5, "page": 0, "delay": 0, "rtl": False}, "$35", "35"),
}


async def _slider(session: NotteSession, options: dict[str, int | bool]) -> None:
    page = SLIDER.replace("OPTIONS", json.dumps(options))
    _ = await session.window.page.goto(f"data:text/html,{quote(page)}")


@pytest.mark.asyncio
@pytest.mark.parametrize(("options", "value", "expected"), CASES.values(), ids=CASES.keys())
async def test_fill_moves_a_slider_to_the_value(options: dict[str, int | bool], value: str, expected: str) -> None:
    async with NotteSession(headless=True) as session:
        await _slider(session, options)
        result = await session.aexecute(FillAction(selector="#slider", value=value), raise_on_failure=True)
        assert result.success
        assert await session.window.page.locator("#slider").get_attribute("aria-valuenow") == expected


@pytest.mark.asyncio
async def test_fill_fails_on_a_slider_without_a_number_or_keyboard() -> None:
    async with NotteSession(headless=True) as session:
        await _slider(session, {"step": 10, "page": 0, "delay": 0, "rtl": False})
        result = await session.aexecute(FillAction(selector="#slider", value="cheap"), raise_on_failure=False)
        assert not result.success and "takes a number" in result.message

        # a slider that ignores the keyboard
        await _slider(session, {"step": 0, "page": 0, "delay": 0, "rtl": False})
        result = await session.aexecute(FillAction(selector="#slider", value="50"), raise_on_failure=False)
        assert not result.success and "does not move with its keyboard" in result.message
        assert await session.window.page.locator("#slider").get_attribute("aria-valuenow") == "20"
