import os
from unittest.mock import patch

import pytest
from notte_browser.tagging.action.llm_taging.listing import ActionListingPipe
from notte_browser.tagging.action.llm_taging.parser import ActionListingParserPipe, ActionListingParserType
from notte_core.actions import WaitAction
from notte_core.browser.dom_tree import A11yNode, A11yTree, ComputedDomAttributes, DomNode
from notte_core.browser.node_type import NodeType
from notte_core.browser.snapshot import BrowserSnapshot, SnapshotMetadata, ViewportData
from notte_core.common.config import PerceptionType

import notte
from tests.mock.mock_service import MockLLMService
from tests.mock.mock_service import patch_llm_service as _patch_llm_service

patch_llm_service = _patch_llm_service


@pytest.fixture
def action_list_answer() -> str:
    return """
# Discovery & Exploration
* L37: Shows flights from London to Tokyo
* B30: Explores available flights

# Search & Input
* I3: Selects the origin location (origin: str)
* I1: Selects the ticket type (ticketType: str = [Round trip, One way, Multi-city])
* B6: Changes the number of passengers
* I6: Enters the return date (returnDate: date)

"""


@pytest.fixture
def action_table_answer() -> str:
    return "\n".join(
        [
            "| ID  | Description | Parameters | Category |",
            "| L37 | Shows flights from London to Tokyo | | Discovery & Exploration |",
            "| B30 | Explores available flights | | Discovery & Exploration |",
            "| I3  | Selects the origin location | name: origin: type: str | Search & Input |",
            (
                "| I1  | Selects the ticket type | name: ticketType: type: str, "
                'default="Round trip", values=["Round trip", "One way", "Multi-city"]'
                " | Search & Input |"
            ),
            "| B6  | Changes the number of passengers | | Search & Input |",
            "| I6  | Enters the return date | name: returnDate: type: date | Search & Input |",
        ]
    )


@pytest.fixture
def mock_snapshot() -> BrowserSnapshot:
    return BrowserSnapshot(
        metadata=SnapshotMetadata(
            title="mock",
            url="https://www.google.com/travel/flights",
            viewport=ViewportData(
                scroll_x=0,
                scroll_y=0,
                viewport_width=1000,
                viewport_height=1000,
                total_width=1000,
                total_height=1000,
            ),
            tabs=[],
        ),
        html_content="html-content",
        a11y_tree=A11yTree(
            raw=A11yNode(
                id="B2",
                role="button",
                name="user-text",
            ),
            simple=A11yNode(
                id="B2",
                role="button",
                name="user-text",
            ),
        ),
        dom_node=DomNode(
            id="B2",
            role="button",
            text="user-text",
            type=NodeType.INTERACTION,
            children=[],
            attributes=None,
            computed_attributes=ComputedDomAttributes(),
        ),
        screenshot=b"screenshot",
    )


@pytest.mark.parametrize(
    "parser,mock_response",
    [
        (ActionListingParserType.MARKDOWN, "action_list_answer"),
        (ActionListingParserType.TABLE, "action_table_answer"),
    ],
)
@pytest.mark.asyncio
async def test_listing_pipe(
    mock_snapshot: BrowserSnapshot,
    parser: ActionListingParserType,
    mock_response: str,
    request: pytest.FixtureRequest,
) -> None:
    # Get the actual response string from the fixture
    response = request.getfixturevalue(mock_response)

    llm_service = MockLLMService(
        mock_response=f"""
<document-summary>
This is a mock document summary
</document-summary>
<document-category>
homepage
</document-category>
<action-listing>
{response}
</action-listing>
"""
    )

    pipe: ActionListingPipe = ActionListingPipe(llmserve=llm_service)
    with patch.object(ActionListingParserPipe, "type", parser):
        assert ActionListingParserPipe.type == parser
        actions = (await pipe.forward(snapshot=mock_snapshot)).actions

        # Test common expectations
        assert len(actions) == 6  # Total number of actions
        # Action 0
        assert actions[0].id == "L37"
        assert actions[0].description == "Shows flights from London to Tokyo"
        assert actions[0].category == "Discovery & Exploration"
        assert actions[0].param is None

        # Action 1
        assert actions[1].id == "B30"
        assert actions[1].description == "Explores available flights"
        assert actions[1].category == "Discovery & Exploration"
        assert actions[1].param is None

        # Action 2
        assert actions[2].id == "I3"
        assert actions[2].description == "Selects the origin location"
        assert actions[2].category == "Search & Input"
        assert actions[2].param is not None
        assert actions[2].param.name == "origin"
        assert actions[2].param.type == "str"
        assert actions[2].param.default is None
        assert actions[2].param.values == []

        # Action 3
        assert actions[3].id == "I1"
        assert actions[3].description == "Selects the ticket type"
        assert actions[3].category == "Search & Input"
        assert actions[3].param is not None
        assert actions[3].param.name == "ticketType"
        assert actions[3].param.type == "str"
        if parser is ActionListingParserType.MARKDOWN:
            assert actions[3].param.default is None
        else:
            assert actions[3].param.default == "Round trip"
        assert actions[3].param.values == ["Round trip", "One way", "Multi-city"]

        # Action 4
        assert actions[4].id == "B6"
        assert actions[4].description == "Changes the number of passengers"
        assert actions[4].category == "Search & Input"
        assert actions[4].param is None

        # Action 5
        assert actions[5].id == "I6"
        assert actions[5].description == "Enters the return date"
        assert actions[5].category == "Search & Input"
        assert actions[5].param is not None
        assert actions[5].param.name == "returnDate"
        assert actions[5].param.type == "date"
        assert actions[5].param.default is None
        assert actions[5].param.values == []


@pytest.mark.asyncio
async def test_groundtruth_interactions():
    async with notte.Session(headless=True, viewport_width=1280, viewport_height=720) as session:
        file_path = "tests/data/duckduckgo.html"
        _ = await session.window.page.goto(url=f"file://{os.path.abspath(file_path)}")

        res = await session.aexecute(WaitAction(time_ms=100))
        assert res.success
        obs = await session.aobserve(perception_type=PerceptionType.FAST)
        actions = obs.space.interaction_actions

        action_ids = [action.id for action in actions]

        assert action_ids == ["L1", "F1", "I1", "B1", "L2", "B2", "F2", "L3", "F3", "L4", "L5"]
