"""A fill on an ARIA slider (`role="slider"`) or spinbutton (`role="spinbutton"`) moves it to the value with its keyboard.

`locator.fill` rejects such an element (it is not an input), so no action could set a custom slider
(noUiSlider, MUI, Radix). The keys are the ones https://www.w3.org/WAI/ARIA/apg/patterns/slider/ defines.
"""

import json
from urllib.parse import quote

import pytest
from notte_browser import execution
from notte_browser.session import NotteSession
from notte_core.actions import FillAction

# A slider from 0 to 100 that moves by `step` with the arrows and by `page` with Page Up / Down (0: not
# handled), `delay` ms after the key (a slider that re-renders), with Left / Right swapped when `rtl`, only
# Left / Right handled when `horizontal`, and its element replaced by a new one on each move when `replace`.
SLIDER = """<div id="slider" role="ROLE" tabindex="0" aria-label="Price" aria-valuemin="0" aria-valuemax="100"
aria-valuenow="20" style="width: 200px; height: 20px; background: #ccc"></div>
<script>
const {step, page, delay, rtl, horizontal, replace} = Object.assign({horizontal: false, replace: false}, OPTIONS);
let slider = document.getElementById("slider");
const moves = {ArrowRight: rtl ? -step : step, ArrowLeft: rtl ? step : -step, Home: -1000, End: 1000};
if (!horizontal) Object.assign(moves, {ArrowUp: step, ArrowDown: -step});
if (page) Object.assign(moves, {PageUp: page, PageDown: -page});
function onKey(event) {
    if (!(event.key in moves)) return;
    event.preventDefault();
    const value = Math.min(100, Math.max(0, Number(slider.getAttribute("aria-valuenow")) + moves[event.key]));
    setTimeout(() => {
        if (!replace) return slider.setAttribute("aria-valuenow", String(value));
        const next = slider.cloneNode();
        next.setAttribute("aria-valuenow", String(value));
        next.addEventListener("keydown", onKey);
        slider.replaceWith(next);
        slider = next;
    }, delay);
}
slider.addEventListener("keydown", onKey);
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
    "a leading-dot decimal": ({"step": 0.5, "page": 0, "delay": 0, "rtl": False}, ".5", "0.5"),
    "an exponent": ({"step": 10, "page": 0, "delay": 0, "rtl": False}, "5e1", "50"),
    # each update lands after the 150 ms a key was waited for before: a key is not taken as doing nothing
    "updated late, page keys then arrows": ({"step": 1, "page": 10, "delay": 200, "rtl": False}, "32", "32"),
    # Right decreases it and there are no Up / Down keys: the pair is swapped
    "reversed, Left / Right only": ({"step": 10, "page": 0, "delay": 0, "rtl": True, "horizontal": True}, "50", "50"),
    "its element replaced on each move": (
        {"step": 10, "page": 0, "delay": 0, "rtl": False, "replace": True},
        "60",
        "60",
    ),
}


async def _slider(session: NotteSession, options: dict[str, float | bool], role: str = "slider") -> None:
    page = SLIDER.replace("OPTIONS", json.dumps(options)).replace("ROLE", role)
    _ = await session.window.page.goto(f"data:text/html,{quote(page)}")


@pytest.mark.asyncio
@pytest.mark.parametrize(("options", "value", "expected"), CASES.values(), ids=CASES.keys())
async def test_fill_moves_a_slider_to_the_value(options: dict[str, float | bool], value: str, expected: str) -> None:
    async with NotteSession(headless=True) as session:
        await _slider(session, options)
        result = await session.aexecute(FillAction(selector="#slider", value=value), raise_on_failure=True)
        assert result.success
        assert await session.window.page.locator("#slider").get_attribute("aria-valuenow") == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("options", "value", "expected"),
    [
        ({"step": 1, "page": 10, "delay": 0, "rtl": False}, "37", "37"),
        ({"step": 2, "page": 0, "delay": 0, "rtl": False}, "8", "8"),
    ],
    ids=["page keys then arrows", "arrows down"],
)
async def test_fill_moves_a_spinbutton_to_the_value(
    options: dict[str, float | bool], value: str, expected: str
) -> None:
    # a custom spinbutton (a div with the role, as the APG toolbar's font size), not a native number input
    async with NotteSession(headless=True) as session:
        await _slider(session, options, role="spinbutton")
        result = await session.aexecute(FillAction(selector="#slider", value=value), raise_on_failure=True)
        assert result.success
        assert await session.window.page.locator("#slider").get_attribute("aria-valuenow") == expected


@pytest.mark.asyncio
async def test_fill_reaches_the_value_on_the_last_key_it_may_press(monkeypatch: pytest.MonkeyPatch) -> None:
    # 20 to 70 by 10: 5 presses, all the arrows may press
    monkeypatch.setattr(execution, "MAX_SLIDER_KEYS", 5)
    async with NotteSession(headless=True) as session:
        await _slider(session, {"step": 10, "page": 0, "delay": 0, "rtl": False})
        result = await session.aexecute(FillAction(selector="#slider", value="70"), raise_on_failure=False)
        assert result.success, result.message
        assert await session.window.page.locator("#slider").get_attribute("aria-valuenow") == "70"


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
