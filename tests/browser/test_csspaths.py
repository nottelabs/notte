"""The DOM builder extends each element's CSS path from its parent's (`child_css_path`) instead of converting
every XPath from scratch: the result must be what `xpath_to_css_path` gives for the element's own XPath."""

import pytest
from notte_browser.dom.builder import RawFrame, RawNode, build_dom_tree
from notte_browser.dom.csspaths import child_css_path, xpath_to_css_path


@pytest.mark.parametrize(
    ("parent_xpath", "xpath"),
    [
        # one step below the parent
        ("html/body", "html/body/div"),
        ("html/body/div[2]", "html/body/div[2]/a[3]"),
        ("/html/body", "/html/body/ul/li[last()]"),
        ("html/body/ul", "html/body/ul/li[position()>1]"),
        ("html/body/table", "html/body/table/tr[2][1]"),
        ("html/body", "html/body/[2]"),
        # a parent XPath without steps
        ("", "/div"),
        ("/", "//div[2]"),
        # not one step below: converted from scratch
        ("/body", "html/body/div"),
        ("", "div"),
        ("html/body", "html/body/div/span"),
        ("html/body", "html/body/"),
        ("html/body", "html/bodyx/div"),
        ("html/body", "html/body"),
        ("", ""),
    ],
)
def test_child_css_path_is_the_css_path_of_the_xpath(parent_xpath: str, xpath: str) -> None:
    assert child_css_path(parent_xpath, xpath_to_css_path(parent_xpath), xpath) == xpath_to_css_path(xpath)


def test_builder_css_paths_restart_at_shadow_roots() -> None:
    # the payload's XPaths restart below `/body` (the root) and in shadow roots (an empty XPath)
    nodes: dict[str, RawNode] = {
        "0": {"tagName": "body", "xpath": "/body", "attributes": {}, "children": ["1"]},
        "1": {"tagName": "div", "xpath": "html/body/div[2]", "attributes": {}, "children": ["2"], "shadowRoot": True},
        "2": {"tagName": "span", "xpath": "", "attributes": {}, "children": ["3"]},
        "3": {"tagName": "button", "xpath": "button[1]", "attributes": {"type": "button"}, "children": []},
    }
    tree = build_dom_tree(RawFrame(root_id="0", nodes=nodes), url="https://example.test")
    assert tree is not None
    css_paths = [
        node.computed_attributes.selectors.css_selector
        for node in tree.flatten()
        if node.computed_attributes.selectors is not None
    ]
    assert css_paths == ["body", "html > body > div:nth-of-type(2)", "", 'button:nth-of-type(1)[type="button"]']
