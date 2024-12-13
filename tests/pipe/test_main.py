from unittest.mock import patch

import pytest

from notte.actions.base import Action
from notte.browser.context import Context
from notte.browser.node_type import NodeAttributesPre, NodeRole, NotteNode
from notte.pipe.main import ContextToActionSpacePipe
from tests.mock.mock_service import MockLLMService


@pytest.fixture
def mock_previous_actions() -> list[Action]:
    return [Action(id="L1", description="", category="", params=[])]


@pytest.fixture
def mock_context() -> Context:
    return Context(
        node=NotteNode(
            id="B1",
            role=NodeRole.BUTTON,
            text="",
            children=[],
            attributes_pre=NodeAttributesPre(),
            attributes_post=None,
        ),
        snapshot=None,
    )


@pytest.fixture
def mock_context_actions() -> list[Action]:
    return [Action(id="B1", description="", category="", params=[])]


def patched_action_listing_identity(context: Context, previous_action_list: list[Action] | None) -> list[Action]:
    return [Action(id=node.id, description="", category="", params=[]) for node in context.interaction_nodes()]


def test_previous_actions_ids_not_in_context_inodes_not_listed(
    mock_context: Context, mock_context_actions: list[Action]
) -> None:
    llmservce = MockLLMService(mock_response="")
    pipe = ContextToActionSpacePipe(llmserve=llmservce)
    with patch(
        "notte.pipe.listing.MarkdownTableActionListingPipe.forward", side_effect=patched_action_listing_identity
    ):
        action_space = pipe.forward(mock_context, mock_context_actions)
        assert [a.id for a in action_space.actions("valid")] == [a.id for a in mock_context_actions]
