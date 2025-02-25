import pytest

from notte.browser.dom_tree import A11yNode
from notte.pipe.preprocessing.a11y.conflict_resolution import (
    format_path_for_conflict_resolution,
    get_first_parent_with_text_elements,
)
from notte.pipe.preprocessing.a11y.traversal import find_node_path_by_role_and_name


@pytest.fixture
def node() -> A11yNode:
    return A11yNode(
        role="WebArea",
        name="",
        children=[
            A11yNode(
                role="group",
                name="",
                children=[
                    A11yNode(
                        role="text",
                        name="text 1",
                        children=[],
                    ),
                    A11yNode(
                        role="text",
                        name="text 2",
                        children=[],
                    ),
                    A11yNode(
                        role="text",
                        name="text 3",
                        children=[],
                    ),
                    A11yNode(
                        role="group",
                        name="",
                        children=[
                            A11yNode(
                                role="text",
                                name="text 4",
                                children=[],
                            ),
                            A11yNode(
                                role="text",
                                name="text 5",
                                children=[],
                            ),
                            A11yNode(
                                role="group",
                                name="",
                                children=[
                                    A11yNode(
                                        role="text",
                                        name="text 6",
                                        children=[],
                                    ),
                                    A11yNode(
                                        role="text",
                                        name="text 7",
                                        children=[],
                                    ),
                                    A11yNode(
                                        role="button",
                                        name="button 1",
                                        children=[],
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
            A11yNode(
                role="group",
                name="",
                children=[
                    A11yNode(
                        role="group",
                        name="",
                        children=[
                            A11yNode(
                                role="link",
                                name="link 1",
                                children=[],
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


def test_format_path_for_conflict_resolution() -> None:
    with pytest.raises(ValueError, match="Node path is None"):
        _ = format_path_for_conflict_resolution(None)

    with pytest.raises(ValueError, match="Node path should have at least two nodes"):
        _ = format_path_for_conflict_resolution([A11yNode(role="WebArea", name="", children=[])])

    with pytest.raises(ValueError, match="The first node in the node path should be the root node"):
        _ = format_path_for_conflict_resolution(
            [
                A11yNode(role="group", name="", children=[]),
                A11yNode(role="group", name="", children=[]),
            ]
        )

    path = [
        A11yNode(role="button", name="button 1", children=[]),
        A11yNode(role="group", name="", children=[]),
        A11yNode(role="group", name="", children=[]),
        A11yNode(role="group", name="", children=[]),
        A11yNode(role="group", name="", children=[]),
        A11yNode(role="WebArea", name="", children=[]),
    ]
    node, node_path = format_path_for_conflict_resolution(path)
    assert node == path[0]
    assert node_path[0] == path[-1]
    assert node_path[1] == path[-2]
    assert node_path[2] == path[-3]
    assert node_path[3] == path[-4]
    assert node_path[4] == path[-5]


def test_increase_depth_leads_to_more_text_names(node: A11yNode) -> None:
    _node_path = find_node_path_by_role_and_name(node, "button", "button 1")
    if _node_path is None:
        raise ValueError("Node path not found")
    node, node_path = format_path_for_conflict_resolution(_node_path)

    min_depths = [1, 2, 3, 4]
    len_last_text_names = 0
    for min_depth in min_depths:
        depth, text_names = get_first_parent_with_text_elements(
            node, node_path, min_depth=min_depth, min_nb_text_names=len_last_text_names
        )
        if depth is None:
            break
        assert len(text_names) > 0, "All nodes should have text names for button 1"
        if len(text_names) < len_last_text_names:
            raise ValueError(
                f"The number of text names is decreasing: {len_last_text_names}"
                f" -> {len(text_names)} at depth {min_depth}"
            )
        len_last_text_names = len(text_names)
    assert len_last_text_names > 0


def test_path_with_no_text_names_returns_none(node: A11yNode) -> None:
    node_path = find_node_path_by_role_and_name(node, "link", "link 1")
    if node_path is None:
        raise ValueError("Node path not found")
    depth, text_names = get_first_parent_with_text_elements(node, node_path)
    assert depth is None
    assert len(text_names) == 0
