"""`buildDomNode.js` gives an element's XPath as its last step (`xpathStep`) when the XPath is its parent's
(in the payload) followed by that step, and the builder joins them back. The XPaths must be the same as the
whole XPaths the script computes, where a step depends on its context: same-tag siblings (also when some are
not in the payload), shadow roots, iframes, `<body>`, text and SVG content, contenteditable elements."""

import json
from typing import Any
from urllib.parse import quote

import pytest
from notte_browser.dom import parsing
from notte_browser.dom.builder import RawFrame, RawNode, build_dom_tree
from notte_browser.session import NotteSession

PAGE = """
<div id="list">
  <p style="position: absolute; top: -9999px; width: 0; height: 0"></p>
  <p>First <b>bold</b></p>
  <button>One</button>
  <button>Two <svg width="10" height="10"><title>icon</title><rect width="10" height="10"></rect></svg></button>
</div>
<div contenteditable="true"><span>Editable <i>text</i></span></div>
<my-host></my-host>
<iframe srcdoc="<div><span><button>Framed</button></span></div>"></iframe>
<script>
  document.querySelector("my-host").attachShadow({ mode: "open" }).innerHTML =
    "<div><button>Shadow</button></div><button>Direct</button>";
</script>
"""

ARGS: dict[str, Any] = {
    "highlight_elements": True,
    "focus_element": -1,
    "viewport_expansion": 0,
    "enable_pointer_elements": True,
    "frame_elements": [],
    "collect_elements": False,
}


async def _open(session: NotteSession) -> None:
    _ = await session.window.page.goto(f"data:text/html,{quote(PAGE)}")
    _ = await session.window.page.frames[1].wait_for_selector("button")


@pytest.mark.asyncio
async def test_xpaths_rebuilt_from_steps() -> None:
    async with NotteSession(headless=True, viewport_width=1280, viewport_height=720) as session:
        await _open(session)
        _ = await session.aobserve()
        xpaths = {
            (node.get_role_str(), node.inner_text()): node.computed_attributes.selectors.xpath_selector
            for node in session.snapshot.dom_node.flatten()
            if node.computed_attributes.selectors is not None and node.attributes is not None
        }
        expected = {
            # the children of `<body>` (`/body` in the payload) have whole XPaths
            "html/body/div[1]",
            "html/body/div[2]",
            "html/body/my-host",
            "html/body/iframe",
            # the first `<p>` is not in the payload (no size, outside the viewport): the second keeps its index
            "html/body/div[1]/p[2]",
            "html/body/div[1]/p[2]/b",
            "html/body/div[1]/button[1]",
            # the SVG is not in the payload
            "html/body/div[1]/button[2]",
            "html/body/div[2]/span",
            "html/body/div[2]/span/i",
            # XPaths restart in a shadow root: each of its children has its own step
            "div",
            "div/button",
            "button",
            # and in the frame's document
            "/body",
            "html/body/div",
            "html/body/div/span",
            "html/body/div/span/button",
        }
        assert set(xpaths.values()) == expected
        assert xpaths[("button", "One")] == "html/body/div[1]/button[1]"
        assert xpaths[("button", "Framed")] == "html/body/div/span/button"
        assert xpaths[("button", "Shadow")] == "div/button"
        assert xpaths[("button", "Direct")] == "button"


@pytest.mark.asyncio
async def test_payload_gives_steps_below_the_children_of_body_and_shadow_roots() -> None:
    async with NotteSession(headless=True, viewport_width=1280, viewport_height=720) as session:
        await _open(session)
        payload = json.loads(await session.window.page.evaluate(parsing.DOM_TREE_JS, ARGS))
        nodes: dict[str, RawNode] = payload["map"]
        elements = [node for node in nodes.values() if "tagName" in node]
        by_tag = {node["tagName"]: node for node in elements}  # pyright: ignore[reportTypedDictNotRequiredAccess]
        assert by_tag["body"].get("xpath") == "/body"
        assert by_tag["my-host"].get("xpath") == "html/body/my-host"
        assert by_tag["b"].get("xpathStep") == "b" and "xpath" not in by_tag["b"]
        assert by_tag["i"].get("xpathStep") == "i"
        assert by_tag["span"].get("xpathStep") == "span"
        steps = sorted(node["xpathStep"] for node in elements if "xpathStep" in node)
        # `button` is the shadow button below the shadow root's `div`
        assert steps == ["b", "button", "button[1]", "button[2]", "i", "p[2]", "span"]
        # the children of the shadow root have whole XPaths: they do not extend the host's
        shadow = sorted(node["xpath"] for node in elements if node.get("xpath") in ("div", "button"))
        assert shadow == ["button", "div"]
        # text nodes have no XPath
        assert all("xpath" not in node and "xpathStep" not in node for node in nodes.values() if "text" in node)


def _element(tag: str, children: list[str], xpath: str | None = None, step: str | None = None) -> RawNode:
    node: dict[str, Any] = dict(tagName=tag, attributes={}, children=children, isVisible=True)
    if xpath is not None:
        node["xpath"] = xpath
    if step is not None:
        node["xpathStep"] = step
    return node  # pyright: ignore[reportReturnType]


def test_builder_joins_steps_to_the_parent_in_the_payload_and_in_frames() -> None:
    frame = RawFrame(
        root_id="f0",
        nodes={
            "f0": _element("body", ["f1"], xpath="/body"),
            "f1": _element("div", ["f2"], xpath="html/body/div"),
            "f2": _element("span", ["f3"], step="span[2]"),
            "f3": {"type": "TEXT_NODE", "text": "Framed", "isInViewport": True},
        },
    )
    iframe = _element("iframe", [], xpath="html/body/iframe")
    iframe["frame"] = frame
    nodes: dict[str, RawNode] = {
        "0": _element("body", ["1", "3"], xpath="/body"),
        "1": _element("div", ["2"], xpath="html/body/div"),
        "2": _element("a", [], step="a[3]"),
        "3": iframe,
    }
    tree = build_dom_tree(RawFrame(root_id="0", nodes=nodes), url="https://example.test")
    assert tree is not None
    xpaths = [
        (node.computed_attributes.selectors.xpath_selector, node.computed_attributes.selectors.css_selector)
        for node in tree.flatten()
        if node.computed_attributes.selectors is not None
    ]
    assert xpaths == [
        ("/body", "body"),
        ("html/body/div", "html > body > div"),
        ("html/body/div/a[3]", "html > body > div > a:nth-of-type(3)"),
        ("html/body/iframe", "html > body > iframe"),
        # the frame's root has no parent: its steps join the frame's own XPaths
        ("/body", "body"),
        ("html/body/div", "html > body > div"),
        ("html/body/div/span[2]", "html > body > div > span:nth-of-type(2)"),
    ]
