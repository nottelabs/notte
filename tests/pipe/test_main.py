from typing import Callable
from unittest.mock import patch

from notte.actions.base import Action
from notte.actions.space import ActionSpace, PossibleActionSpace
from notte.browser.dom_tree import DomNode
from notte.browser.node_type import NodeRole
from notte.browser.processed_snapshot import ProcessedBrowserSnapshot
from notte.pipe.main import LlmActionSpacePipe
from tests.mock.mock_service import MockLLMService


def actions_from_ids(ids: list[str]) -> list[Action]:
    return [
        Action(id=id, description="my description", category="my category", params=[], status="valid") for id in ids
    ]


def context_from_ids(ids: list[str]) -> ProcessedBrowserSnapshot:
    return ProcessedBrowserSnapshot(
        node=DomNode(
            id=None,
            role=NodeRole.WEBAREA,
            text="",
            children=[
                DomNode(
                    id=id,
                    role=NodeRole.LINK,
                    text="",
                    children=[],
                )
                for id in ids
            ],
        ),
        snapshot=None,
    )


def llm_patch_from_ids(
    ids: list[str],
) -> Callable[[ProcessedBrowserSnapshot, list[Action] | None], PossibleActionSpace]:
    return lambda context, previous_action_list: PossibleActionSpace(
        description="",
        actions=actions_from_ids(ids),
    )


def context_to_actions(context: ProcessedBrowserSnapshot) -> list[Action]:
    return actions_from_ids(ids=[node.id for node in context.interaction_nodes()])


def space_to_ids(space: ActionSpace) -> list[str]:
    return [a.id for a in space.actions("valid")]


def test_previous_actions_ids_not_in_context_inodes_not_listed() -> None:
    # context[B1] + previous[L1] + llm(B1)=> [B1] not [B1,L1]
    pipe = LlmActionSpacePipe(llmserve=MockLLMService(mock_response=""), categorise_document=False)
    context = context_from_ids(["B1"])
    previous_actions = actions_from_ids(["L1"])
    llm_patch = llm_patch_from_ids(["B1"])
    with patch(
        "notte.pipe.listing.MarkdownTableActionListingPipe.forward",
        side_effect=llm_patch,
    ):
        space = pipe.forward(context, previous_actions)
        assert space_to_ids(space) == ["B1"]


def test_previous_actions_ids_in_context_inodes_listed() -> None:
    # context[B1,L1] + previous[L1] + llm(B1) => [B1,L1]
    pipe = LlmActionSpacePipe(llmserve=MockLLMService(mock_response=""), categorise_document=False)
    context = context_from_ids(["B1", "L1"])
    previous_actions = actions_from_ids(["L1"])
    llm_patch = llm_patch_from_ids(["B1"])
    with patch(
        "notte.pipe.listing.MarkdownTableActionListingPipe.forward",
        side_effect=llm_patch,
    ):
        space = pipe.forward(context, previous_actions)
        assert space_to_ids(space) == ["B1", "L1"]


def test_context_inodes_all_covered_by_previous_actions_listed() -> None:
    # context[B1,L1] + previous[B1,L1] + llm() => [B1,L1]
    pipe = LlmActionSpacePipe(
        llmserve=MockLLMService(mock_response=""),
        categorise_document=False,
        tresh_complete=0,
    )
    context = context_from_ids(["B1", "L1"])
    previous_actions = actions_from_ids(["B1", "L1"])
    llm_patch = llm_patch_from_ids([])
    with patch(
        "notte.pipe.listing.MarkdownTableActionListingPipe.forward",
        side_effect=llm_patch,
    ):
        space = pipe.forward(context, previous_actions)
        assert space_to_ids(space) == ["B1", "L1"]


def test_context_inodes_empty_should_return_empty() -> None:
    # context[] + previous[B1] + llm(C1) => []
    pipe = LlmActionSpacePipe(
        llmserve=MockLLMService(mock_response=""),
        categorise_document=False,
        tresh_complete=0,
    )
    context = context_from_ids([])
    previous_actions = actions_from_ids(["B1"])
    llm_patch = llm_patch_from_ids(["C1"])
    with patch(
        "notte.pipe.listing.MarkdownTableActionListingPipe.forward",
        side_effect=llm_patch,
    ):
        space = pipe.forward(context, previous_actions)
        assert space_to_ids(space) == []


def test_context_inodes_empty_previous_returns_llms() -> None:
    # context[B1] + previous[] + llm[B1] => [B1]
    pipe = LlmActionSpacePipe(
        llmserve=MockLLMService(mock_response=""),
        categorise_document=False,
        tresh_complete=0,
    )
    context = context_from_ids(["B1"])
    previous_actions = actions_from_ids([])
    llm_patch = llm_patch_from_ids(["B1"])
    with patch(
        "notte.pipe.listing.MarkdownTableActionListingPipe.forward",
        side_effect=llm_patch,
    ):
        space = pipe.forward(context, previous_actions)
        assert space_to_ids(space) == ["B1"]

    # context[B1] + previous[] + llm(C1) => []
    context = context_from_ids(["B1"])
    previous_actions = actions_from_ids([])
    llm_patch = llm_patch_from_ids(["C1"])
    with patch(
        "notte.pipe.listing.MarkdownTableActionListingPipe.forward",
        side_effect=llm_patch,
    ):
        space = pipe.forward(context, previous_actions)
        assert space_to_ids(space) == []

    # context[B1] + previous[] + llm() => []
    context = context_from_ids(["B1"])
    previous_actions = actions_from_ids([])
    llm_patch = llm_patch_from_ids([])
    with patch(
        "notte.pipe.listing.MarkdownTableActionListingPipe.forward",
        side_effect=llm_patch,
    ):
        space = pipe.forward(context, previous_actions)
        assert space_to_ids(space) == []

    # context[B1] + previous[] + llm(B1,B2,C1) => [B1]
    context = context_from_ids(["B1"])
    previous_actions = actions_from_ids([])
    llm_patch = llm_patch_from_ids(["B1", "B2", "C1"])
    with patch(
        "notte.pipe.listing.MarkdownTableActionListingPipe.forward",
        side_effect=llm_patch,
    ):
        space = pipe.forward(context, previous_actions)
        assert space_to_ids(space) == ["B1"]
