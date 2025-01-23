import pytest

from notte.actions.parsing import ActionListingParser
from notte.browser.context import Context
from notte.browser.node_type import A11yNode, A11yTree, NotteNode
from notte.browser.snapshot import BrowserSnapshot, SnapshotMetadata
from notte.pipe.listing import MarkdownTableActionListingPipe
from tests.mock.mock_service import MockLLMService


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
def mock_context() -> Context:
    return Context(
        node=NotteNode(
            id="B6",
            role="button",
            text="Changes the number of passengers",
            children=[
                NotteNode(
                    id="I6",
                    role="input",
                    text="Enters the return date",
                ),
            ],
        ),
        snapshot=BrowserSnapshot(
            metadata=SnapshotMetadata(
                title="mock",
                url="https://www.google.com/travel/flights",
            ),
            html_content="html-content",
            a11y_tree=A11yTree(
                raw=A11yNode(
                    id="L37",
                    role="link",
                    name="Shows flights from London to Tokyo",
                    children=[
                        A11yNode(
                            id="I6",
                            role="input",
                            name="Selects the origin location",
                        ),
                    ],
                ),
                simple=A11yNode(
                    id="L37",
                    role="link",
                    name="Shows flights from London to Tokyo",
                    children=[
                        A11yNode(
                            id="I6",
                            role="input",
                            name="Enters the return date",
                        ),
                    ],
                ),
            ),
            screenshot=b"screenshot",
        ),
    )


@pytest.mark.parametrize(
    "parser,mock_response",
    [(ActionListingParser.MARKDOWN, "action_list_answer"), (ActionListingParser.TABLE, "action_table_answer")],
)
def test_listing_pipe(
    mock_context: Context, parser: ActionListingParser, mock_response: str, request: pytest.FixtureRequest
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

    pipe: MarkdownTableActionListingPipe = MarkdownTableActionListingPipe(llmserve=llm_service)
    pipe.parser = parser
    actions = pipe.forward(context=mock_context).actions

    # Test common expectations
    assert len(actions) == 6  # Total number of actions
    # Action 0
    assert actions[0].id == "L37"
    assert actions[0].description == "Shows flights from London to Tokyo"
    assert actions[0].category == "Discovery & Exploration"
    assert len(actions[0].params) == 0

    # Action 1
    assert actions[1].id == "B30"
    assert actions[1].description == "Explores available flights"
    assert actions[1].category == "Discovery & Exploration"
    assert len(actions[1].params) == 0

    # Action 2
    assert actions[2].id == "I3"
    assert actions[2].description == "Selects the origin location"
    assert actions[2].category == "Search & Input"
    assert len(actions[2].params) == 1
    assert actions[2].params[0].name == "origin"
    assert actions[2].params[0].type == "str"
    assert actions[2].params[0].default is None
    assert actions[2].params[0].values == []

    # Action 3
    assert actions[3].id == "I1"
    assert actions[3].description == "Selects the ticket type"
    assert actions[3].category == "Search & Input"
    assert len(actions[3].params) == 1
    assert actions[3].params[0].name == "ticketType"
    assert actions[3].params[0].type == "str"
    # assert actions[3].params[0].default == None
    assert actions[3].params[0].values == ["Round trip", "One way", "Multi-city"]

    # Action 4
    assert actions[4].id == "B6"
    assert actions[4].description == "Changes the number of passengers"
    assert actions[4].category == "Search & Input"
    assert len(actions[4].params) == 0

    # Action 5
    assert actions[5].id == "I6"
    assert actions[5].description == "Enters the return date"
    assert actions[5].category == "Search & Input"
    assert len(actions[5].params) == 1
    assert actions[5].params[0].name == "returnDate"
    assert actions[5].params[0].type == "date"
    assert actions[5].params[0].default is None
    assert actions[5].params[0].values == []
