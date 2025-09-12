from collections.abc import Sequence
from typing import Callable
from unittest.mock import patch

import pytest
from notte_browser.tagging.action.llm_taging.pipe import LlmActionSpacePipe
from notte_browser.tagging.type import PossibleAction, PossibleActionSpace
from notte_core.actions import ClickAction, InteractionAction
from notte_core.browser.dom_tree import A11yTree, ComputedDomAttributes, DomNode
from notte_core.browser.node_type import NodeRole, NodeType
from notte_core.browser.snapshot import BrowserSnapshot, SnapshotMetadata, ViewportData
from notte_core.space import ActionSpace
from notte_sdk.types import PaginationParams

from tests.mock.mock_browser import Observation
from tests.mock.mock_service import MockLLMService
from tests.mock.mock_service import patch_llm_service as _patch_llm_service

patch_llm_service = _patch_llm_service


@pytest.fixture
def mock_llm_service() -> MockLLMService:
    return MockLLMService(mock_response="")


def interaction_actions_from_ids(ids: list[str]) -> Sequence[ClickAction]:
    return [
        ClickAction(
            id=id,
            description="my description",
            category="my category",
            param=None,
        )
        for id in ids
    ]


def possible_actions_from_ids(ids: list[str]) -> Sequence[PossibleAction]:
    return [
        PossibleAction(
            id=id,
            description="my description",
            category="my category",
        )
        for id in ids
    ]


@pytest.fixture
def listing_config():
    with patch.object(LlmActionSpacePipe, "required_action_coverage", 0.0):
        with patch.object(LlmActionSpacePipe, "doc_categorisation", False):
            yield


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
        screenshot=Observation.empty().screenshot.raw,
    )


def llm_patch_from_ids(
    ids: list[str],
) -> Callable[[BrowserSnapshot, Sequence[InteractionAction] | None], PossibleActionSpace]:
    return lambda context, previous_action_list: PossibleActionSpace(
        description="",
        actions=possible_actions_from_ids(ids),
    )


def context_to_actions(snapshot: BrowserSnapshot) -> Sequence[InteractionAction]:
    return interaction_actions_from_ids(ids=[node.id for node in snapshot.interaction_nodes()])


def space_to_ids(space: ActionSpace) -> list[str]:
    return [a.id for a in space.interaction_actions]


@pytest.mark.asyncio
async def test_previous_actions_ids_not_in_context_inodes_not_listed(
    listing_config,
) -> None:
    # context[B1] + previous[L1] + llm(B1)=> [B1] not [B1,L1]
    pipe = LlmActionSpacePipe(
        llmserve=MockLLMService(mock_response=""),
    )
    context = context_from_ids(["B1"])
    previous_actions = interaction_actions_from_ids(["L1"])
    llm_patch = llm_patch_from_ids(["B1"])
    with patch(
        "notte_browser.tagging.action.llm_taging.listing.ActionListingPipe.forward",
        side_effect=llm_patch,
    ):
        space = await pipe.forward(context, previous_actions, pagination=PaginationParams())
        assert space_to_ids(space) == ["B1"]


@pytest.mark.asyncio
async def test_previous_actions_ids_in_context_inodes_listed(
    listing_config,
) -> None:
    # context[B1,L1] + previous[L1] + llm(B1) => [B1,L1]
    pipe = LlmActionSpacePipe(
        llmserve=MockLLMService(mock_response=""),
    )
    context = context_from_ids(["B1", "L1"])
    previous_actions = interaction_actions_from_ids(["L1"])
    llm_patch = llm_patch_from_ids(["B1"])
    with patch(
        "notte_browser.tagging.action.llm_taging.listing.ActionListingPipe.forward",
        side_effect=llm_patch,
    ):
        space = await pipe.forward(context, previous_actions, pagination=PaginationParams())
        assert space_to_ids(space) == ["B1", "L1"]


@pytest.mark.asyncio
async def test_context_inodes_all_covered_by_previous_actions_listed(
    listing_config, patch_llm_service: MockLLMService
) -> None:
    # context[B1,L1] + previous[B1,L1] + llm() => [B1,L1]
    pipe = LlmActionSpacePipe(
        llmserve=patch_llm_service,
    )
    context = context_from_ids(["B1", "L1"])
    previous_actions = interaction_actions_from_ids(["B1", "L1"])
    llm_patch = llm_patch_from_ids([])
    with patch(
        "notte_browser.tagging.action.llm_taging.listing.ActionListingPipe.forward",
        side_effect=llm_patch,
    ):
        space = await pipe.forward(context, previous_actions, pagination=PaginationParams())
        assert space_to_ids(space) == ["B1", "L1"]


@pytest.mark.asyncio
async def test_context_inodes_empty_should_return_empty(
    listing_config,
) -> None:
    # context[] + previous[B1] + llm(C1) => []
    pipe = LlmActionSpacePipe(
        llmserve=MockLLMService(mock_response=""),
    )
    context = context_from_ids([])
    previous_actions = interaction_actions_from_ids(["B1"])
    llm_patch = llm_patch_from_ids(["C1"])
    with patch(
        "notte_browser.tagging.action.llm_taging.listing.ActionListingPipe.forward",
        side_effect=llm_patch,
    ):
        space = await pipe.forward(context, previous_actions, pagination=PaginationParams())
        assert space_to_ids(space) == []


@pytest.mark.asyncio
async def test_context_inodes_empty_previous_returns_llms(listing_config, patch_llm_service: MockLLMService) -> None:
    # context[B1] + previous[] + llm[B1] => [B1]
    pipe = LlmActionSpacePipe(
        llmserve=patch_llm_service,
    )
    context = context_from_ids(["B1"])
    previous_actions = interaction_actions_from_ids([])
    llm_patch = llm_patch_from_ids(["B1"])
    with patch(
        "notte_browser.tagging.action.llm_taging.listing.ActionListingPipe.forward",
        side_effect=llm_patch,
    ):
        space = await pipe.forward(context, previous_actions, pagination=PaginationParams())
        assert space_to_ids(space) == ["B1"]

    # context[B1] + previous[] + llm(C1) => []
    context = context_from_ids(["B1"])
    previous_actions = interaction_actions_from_ids([])
    llm_patch = llm_patch_from_ids(["C1"])
    with patch(
        "notte_browser.tagging.action.llm_taging.listing.ActionListingPipe.forward",
        side_effect=llm_patch,
    ):
        space = await pipe.forward(context, previous_actions, pagination=PaginationParams())
        assert space_to_ids(space) == []

    # context[B1] + previous[] + llm() => []
    context = context_from_ids(["B1"])
    previous_actions = interaction_actions_from_ids([])
    llm_patch = llm_patch_from_ids([])
    with patch(
        "notte_browser.tagging.action.llm_taging.listing.ActionListingPipe.forward",
        side_effect=llm_patch,
    ):
        space = await pipe.forward(context, previous_actions, pagination=PaginationParams())
        assert space_to_ids(space) == []

    # context[B1] + previous[] + llm(B1,B2,C1) => [B1]
    context = context_from_ids(["B1"])
    previous_actions = interaction_actions_from_ids([])
    llm_patch = llm_patch_from_ids(["B1", "B2", "C1"])
    with patch(
        "notte_browser.tagging.action.llm_taging.listing.ActionListingPipe.forward",
        side_effect=llm_patch,
    ):
        space = await pipe.forward(context, previous_actions, pagination=PaginationParams())
        assert space_to_ids(space) == ["B1"]
