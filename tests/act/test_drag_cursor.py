"""Draggable targets retain click controls and disclose the unsupported drag capability."""

from urllib.parse import quote

import pytest
from notte_browser.session import NotteSession
from notte_core.element_state import ElementState, page_fingerprint

from tests.act.fakes import FakeDecider


@pytest.mark.parametrize("cursor", ["grab", "grabbing"])
@pytest.mark.parametrize("hover", [False, True])
@pytest.mark.asyncio
async def test_draggable_targets_disclose_drag_capability_without_hiding_clicks(cursor: str, hover: bool) -> None:
    selector = ".drag:hover" if hover else ".drag"
    page = f"""
        <style>{selector} {{ cursor: {cursor}; }} .drag {{ padding: 8px; }}</style>
        <ol><li class="drag" draggable="true">Reorder this card</li></ol>
        <div class="drag">Drag this handle</div>
        <button class="drag" draggable="true">Open card</button>
        <a class="drag" draggable="true" href="#details">View details</a>
        <a href="#normal">Ordinary link</a>
        <button draggable="false">Non-draggable button</button>
        <div class="drag" role="button" tabindex="0">Card menu</div>
        <div class="drag" draggable="true" onclick="this.textContent='Selected'">Select card</div>
        <div class="drag" draggable="true" id="property">Property handler</div>
        <div style="cursor:pointer">Pointer control</div>
        <div class="drag" draggable="true"><button>Nested control</button></div>
        <script>document.getElementById('property').onclick = function () {{ this.textContent='Selected'; }};</script>
    """
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
        observation = await session.aobserve()
        labels = {action.accessible_name or action.text_label for action in observation.space.interaction_actions}
        assert "Reorder this card" in observation.space.description
        assert "Drag this handle" in observation.space.description
        assert labels == {
            "Reorder this card",
            "Drag this handle",
            "Open card",
            "View details",
            "Ordinary link",
            "Non-draggable button",
            "Card menu",
            "Select card",
            "Property handler",
            "Pointer control",
            "Nested control",
        }

        decider = FakeDecider(choices=[{"operation": "BLOCKED"}])
        result = await session.aact("Reorder this card", decider=decider, raise_on_failure=False)
        assert result.status == "blocked"
        assert {element["label"] for element in decider.states[0].elements} == labels
        draggable = {element["label"] for element in decider.states[0].elements if element.get("draggable") is True}
        assert draggable == {"Reorder this card", "Open card", "View details", "Select card", "Property handler"}
        targets = decider.questions[0]["click_target"].criteria
        assert len(targets) == len(labels)
        operations = decider.questions[0]["operation"].criteria
        assert "DRAG" not in operations
        assert "drag and drop is not supported by act()" in operations["BLOCKED"]

        select = next(action for action in observation.space.interaction_actions if action.text_label == "Select card")
        executed = await session.aexecute(select)
        assert executed.success
        assert await session.window.page.locator(".drag[onclick]").inner_text() == "Selected"

        property_click = next(
            action for action in observation.space.interaction_actions if action.text_label == "Property handler"
        )
        executed = await session.aexecute(property_click)
        assert executed.success
        assert await session.window.page.locator("#property").inner_text() == "Selected"


@pytest.mark.asyncio
async def test_a_changed_draggable_state_invalidates_a_click_decision() -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(
            "data:text/html," + quote('<button draggable="true" onclick="this.textContent=\'Opened\'">Card</button>')
        )
        observation = await session.aobserve()
        target = observation.space.interaction_actions[0].id

        async def stop_dragging() -> None:
            await session.window.page.locator("button").evaluate("el => el.draggable = false")

        decider = FakeDecider(
            choices=[{"operation": "CLICK", "click_target": target}] * 2,
            on_choose=stop_dragging,
        )
        result = await session.aact("Open the card", decider=decider)
        assert result.status == "executed" and result.success
        assert len(decider.states) == 2
        assert decider.states[0].elements[0]["draggable"] is True
        assert "draggable" not in decider.states[1].elements[0]
        assert await session.window.page.locator("button").inner_text() == "Opened"


def test_draggable_state_is_optional_round_trips_and_changes_the_fingerprint() -> None:
    state = ElementState.from_payload({"draggable": True})
    assert state is not None
    assert ElementState.model_validate_json(state.model_dump_json()).draggable is True
    assert ElementState().draggable is None
    before = page_fingerprint("https://example.test", [("M1", "Card", None)])
    assert before != page_fingerprint("https://example.test", [("M1", "Card", state)])
    for mode in ("validation", "serialization"):
        schema = ElementState.model_json_schema(mode=mode)
        assert schema["type"] == "object"
        assert "draggable" in schema["properties"]
        assert "draggable" not in schema.get("required", [])
