from collections.abc import Sequence
from typing import Callable
from unittest.mock import patch

import pytest
from notte_browser.tagging.action.llm_taging.pipe import LlmActionSpaceConfig, LlmActionSpacePipe
from notte_browser.tagging.types import PossibleActionSpace
from notte_core.actions.percieved import PerceivedAction
from notte_core.actions.space import ActionSpace
from notte_core.browser.dom_tree import A11yTree, ComputedDomAttributes, DomNode
from notte_core.browser.node_type import NodeRole, NodeType
from notte_core.browser.snapshot import BrowserSnapshot, SnapshotMetadata, ViewportData
from notte_sdk.types import PaginationParams

from tests.mock.mock_service import MockLLMService


def actions_from_ids(ids: list[str]) -> Sequence[PerceivedAction]:
    return [
        PerceivedAction(
            id=id,
            description="my description",
            category="my category",
            params=[],
        )
        for id in ids
    ]


@pytest.fixture
def listing_config() -> LlmActionSpaceConfig:
    return LlmActionSpaceConfig(required_action_coverage=0.0, doc_categorisation=False)


def context_from_ids(ids: list[str]) -> BrowserSnapshot:
    return BrowserSnapshot(
        metadata=SnapshotMetadata(
            title="",
            url="",
            viewport=ViewportData(
                viewport_width=1000,
                viewport_height=1000,
                scroll_x=0,
                scroll_y=0,
                total_width=1000,
                total_height=1000,
            ),
            tabs=[],
        ),
        html_content="",
        a11y_tree=A11yTree(
            raw={},
            simple={},
        ),
        dom_node=DomNode(
            id=None,
            role=NodeRole.WEBAREA,
            text="Root Webarea",
            type=NodeType.OTHER,
            attributes=None,
            computed_attributes=ComputedDomAttributes(),
            children=[
                DomNode(
                    id=id,
                    role=NodeRole.LINK,
                    text="",
                    type=NodeType.INTERACTION,
                    children=[],
                    attributes=None,
                    computed_attributes=ComputedDomAttributes(),
                )
                for id in ids
            ],
        ),
        screenshot=None,
    )


def llm_patch_from_ids(
    ids: list[str],
) -> Callable[[BrowserSnapshot, list[PerceivedAction] | None], PossibleActionSpace]:
    return lambda context, previous_action_list: PossibleActionSpace(
        description="",
        actions=actions_from_ids(ids),
    )


def context_to_actions(snapshot: BrowserSnapshot) -> Sequence[PerceivedAction]:
    return actions_from_ids(ids=[node.id for node in snapshot.interaction_nodes()])


def space_to_ids(space: ActionSpace) -> list[str]:
    return [a.id for a in space.actions]


def test_previous_actions_ids_not_in_context_inodes_not_listed(
    listing_config: LlmActionSpaceConfig,
) -> None:
    # context[B1] + previous[L1] + llm(B1)=> [B1] not [B1,L1]
    pipe = LlmActionSpacePipe(
        llmserve=MockLLMService(mock_response=""),
        config=listing_config,
    )
    context = context_from_ids(["B1"])
    previous_actions = actions_from_ids(["L1"])
    llm_patch = llm_patch_from_ids(["B1"])
    with patch(
        "notte_browser.tagging.action.llm_taging.listing.ActionListingPipe.forward",
        side_effect=llm_patch,
    ):
        space = pipe.forward(context, previous_actions, pagination=PaginationParams())
        assert space_to_ids(space) == ["B1"]


def test_previous_actions_ids_in_context_inodes_listed(
    listing_config: LlmActionSpaceConfig,
) -> None:
    # context[B1,L1] + previous[L1] + llm(B1) => [B1,L1]
    pipe = LlmActionSpacePipe(
        llmserve=MockLLMService(mock_response=""),
        config=listing_config,
    )
    context = context_from_ids(["B1", "L1"])
    previous_actions = actions_from_ids(["L1"])
    llm_patch = llm_patch_from_ids(["B1"])
    with patch(
        "notte_browser.tagging.action.llm_taging.listing.ActionListingPipe.forward",
        side_effect=llm_patch,
    ):
        space = pipe.forward(context, previous_actions, pagination=PaginationParams())
        assert space_to_ids(space) == ["B1", "L1"]


def test_context_inodes_all_covered_by_previous_actions_listed(
    listing_config: LlmActionSpaceConfig,
) -> None:
    # context[B1,L1] + previous[B1,L1] + llm() => [B1,L1]
    pipe = LlmActionSpacePipe(
        llmserve=MockLLMService(mock_response=""),
        config=listing_config,
    )
    context = context_from_ids(["B1", "L1"])
    previous_actions = actions_from_ids(["B1", "L1"])
    llm_patch = llm_patch_from_ids([])
    with patch(
        "notte_browser.tagging.action.llm_taging.listing.ActionListingPipe.forward",
        side_effect=llm_patch,
    ):
        space = pipe.forward(context, previous_actions, pagination=PaginationParams())
        assert space_to_ids(space) == ["B1", "L1"]


def test_context_inodes_empty_should_return_empty(
    listing_config: LlmActionSpaceConfig,
) -> None:
    # context[] + previous[B1] + llm(C1) => []
    pipe = LlmActionSpacePipe(
        llmserve=MockLLMService(mock_response=""),
        config=listing_config,
    )
    context = context_from_ids([])
    previous_actions = actions_from_ids(["B1"])
    llm_patch = llm_patch_from_ids(["C1"])
    with patch(
        "notte_browser.tagging.action.llm_taging.listing.ActionListingPipe.forward",
        side_effect=llm_patch,
    ):
        space = pipe.forward(context, previous_actions, pagination=PaginationParams())
        assert space_to_ids(space) == []


def test_context_inodes_empty_previous_returns_llms(
    listing_config: LlmActionSpaceConfig,
) -> None:
    # context[B1] + previous[] + llm[B1] => [B1]
    pipe = LlmActionSpacePipe(
        llmserve=MockLLMService(mock_response=""),
        config=listing_config,
    )
    context = context_from_ids(["B1"])
    previous_actions = actions_from_ids([])
    llm_patch = llm_patch_from_ids(["B1"])
    with patch(
        "notte_browser.tagging.action.llm_taging.listing.ActionListingPipe.forward",
        side_effect=llm_patch,
    ):
        space = pipe.forward(context, previous_actions, pagination=PaginationParams())
        assert space_to_ids(space) == ["B1"]

    # context[B1] + previous[] + llm(C1) => []
    context = context_from_ids(["B1"])
    previous_actions = actions_from_ids([])
    llm_patch = llm_patch_from_ids(["C1"])
    with patch(
        "notte_browser.tagging.action.llm_taging.listing.ActionListingPipe.forward",
        side_effect=llm_patch,
    ):
        space = pipe.forward(context, previous_actions, pagination=PaginationParams())
        assert space_to_ids(space) == []

    # context[B1] + previous[] + llm() => []
    context = context_from_ids(["B1"])
    previous_actions = actions_from_ids([])
    llm_patch = llm_patch_from_ids([])
    with patch(
        "notte_browser.tagging.action.llm_taging.listing.ActionListingPipe.forward",
        side_effect=llm_patch,
    ):
        space = pipe.forward(context, previous_actions, pagination=PaginationParams())
        assert space_to_ids(space) == []

    # context[B1] + previous[] + llm(B1,B2,C1) => [B1]
    context = context_from_ids(["B1"])
    previous_actions = actions_from_ids([])
    llm_patch = llm_patch_from_ids(["B1", "B2", "C1"])
    with patch(
        "notte_browser.tagging.action.llm_taging.listing.ActionListingPipe.forward",
        side_effect=llm_patch,
    ):
        space = pipe.forward(context, previous_actions, pagination=PaginationParams())
        assert space_to_ids(space) == ["B1"]
