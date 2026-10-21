"""`observe()` gives each interaction element its accessible name (`DomNode.accessible_name`, and
`accessible_name` on the actions), as Chromium computes it, without changing the descriptions."""

from collections.abc import AsyncIterator
from urllib.parse import quote

import pytest
import pytest_asyncio
from notte_browser.session import NotteSession
from notte_core.dom_tree import DomNode

PAGE = """
<style>button, .box { width: 40px; height: 20px; } .caps { text-transform: uppercase; }</style>
<span id="first">Search</span> <span id="second">the docs</span>
<input id="labelledby" aria-labelledby="first second">
<label for="labelfor">Email address</label>
<p>Some text between the label and its field.</p>
<div><input id="labelfor" name="email"></div>
<label>Full name <input id="wrapped"></label>
<input id="arialabel" aria-label="Quantity">
<fieldset id="shipping" onclick="">
  <legend>Shipping</legend>
  <label><input id="express" type="radio" name="shipping"> Express</label>
</fieldset>
<a id="imagelink" href="#home"><img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" alt="Home page" width="20" height="20"></a>
<button id="titled" title="Close dialog"></button>
<input id="placeholder" placeholder="Search products">
<input id="submit" type="submit" value="Place order">
<input id="reset" type="reset">
<button id="icon"><svg aria-hidden="true" width="10" height="10"><title>icon</title></svg><span class="caps">Save</span></button>
<a id="upvote" href="#up"><div class="box" title="upvote"></div></a>
<div id="generic" class="box" title="Collapse sidebar" onclick=""></div>
<span id="paytext">Pay</span> <input id="amount" value="100">
<button id="pay" aria-labelledby="paytext amount"></button>
<label id="cardlabel" for="card">Card <input id="cardpart" value="4242"></label> <input id="card">
<div id="host"></div>
<my-field id="slotted"><span slot="label">Slotted name</span></my-field>
<iframe srcdoc="<label for='framed'>Framed field</label><input id='framed'>"></iframe>
<script>
  document.getElementById("host").attachShadow({ mode: "open" }).innerHTML =
    "<label for='inner'>Shadow label</label><input id='inner'>";
  customElements.define("my-field", class extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" }).innerHTML =
        "<label><slot name='label'></slot> <input id='slotinput'></label>";
    }
  });
</script>
"""

EXPECTED = {
    "labelledby": "Search the docs",
    "labelfor": "Email address",
    "wrapped": "Full name",
    "arialabel": "Quantity",
    "shipping": "Shipping",
    "express": "Express",
    "imagelink": "Home page",
    "titled": "Close dialog",
    "placeholder": "Search products",
    "submit": "Place order",
    "reset": "Reset",
    "icon": "SAVE",
    "upvote": None,
    "generic": None,
    # Chromium names these "Pay 100" and "Card 4242": the value of a field never enters a name
    "pay": "Pay",
    "card": "Card",
    "inner": "Shadow label",
    "slotinput": "Slotted name",
    "framed": "Framed field",
}


def _data_url(html: str) -> str:
    return f"data:text/html,{quote(html)}"


@pytest_asyncio.fixture(loop_scope="function")
async def session() -> AsyncIterator[NotteSession]:
    async with NotteSession(headless=True, viewport_width=1280, viewport_height=1600) as session:
        _ = await session.window.page.goto(_data_url(PAGE))
        yield session


def _nodes_by_html_id(session: NotteSession) -> dict[str, DomNode]:
    nodes: dict[str, DomNode] = {}
    for node in session.snapshot.interaction_nodes():
        if node.attributes is not None and node.attributes.id_name is not None:
            nodes[node.attributes.id_name] = node
    return nodes


@pytest.mark.asyncio
async def test_observe_computes_accessible_names(session: NotteSession) -> None:
    obs = await session.aobserve()
    nodes = _nodes_by_html_id(session)

    assert {html_id: nodes[html_id].accessible_name for html_id in EXPECTED} == EXPECTED
    assert nodes["framed"].computed_attributes.selectors is not None
    assert nodes["framed"].computed_attributes.selectors.in_iframe
    assert nodes["inner"].computed_attributes.selectors is not None
    assert nodes["inner"].computed_attributes.selectors.in_shadow_root

    # the actions carry the same name; their text label, used in their messages, is unchanged
    actions = {action.id: action for action in obs.space.interaction_actions}
    for node in nodes.values():
        assert node.id is not None
        assert actions[node.id].accessible_name == node.accessible_name
    labelfor = actions[nodes["labelfor"].id or ""]
    assert labelfor.text_label == "email"
    assert "Email address" not in (labelfor.description or "")


@pytest.mark.asyncio
async def test_names_agree_with_chromium_accessibility_tree(session: NotteSession) -> None:
    _ = await session.aobserve()
    nodes = _nodes_by_html_id(session)
    page = session.window.page
    cdp = await page.context.new_cdp_session(page)
    document = await cdp.send("DOM.getDocument")
    checked = 0
    for html_id, node in nodes.items():
        selectors = node.computed_attributes.selectors
        if html_id in ("pay", "card") or selectors is None or selectors.in_iframe or selectors.in_shadow_root:
            continue
        found = await cdp.send("DOM.querySelector", {"nodeId": document["root"]["nodeId"], "selector": f"#{html_id}"})
        ax = await cdp.send("Accessibility.getPartialAXTree", {"nodeId": found["nodeId"], "fetchRelatives": False})
        chromium_name = " ".join(str(ax["nodes"][0].get("name", {}).get("value", "")).split())
        assert (node.accessible_name or "") == chromium_name, html_id
        checked += 1
    await cdp.detach()
    assert checked >= 14


@pytest.mark.asyncio
async def test_typed_values_never_enter_names(session: NotteSession) -> None:
    page = session.window.page
    await page.fill("#amount", "typed-secret")
    await page.fill("#cardpart", "typed-secret")
    await page.fill("#labelledby", "typed-secret")
    obs = await session.aobserve()

    names = [node.accessible_name or "" for node in session.snapshot.interaction_nodes()]
    assert not any("typed-secret" in name for name in names)
    assert _nodes_by_html_id(session)["pay"].accessible_name == "Pay"
    assert not any("typed-secret" in (action.accessible_name or "") for action in obs.space.interaction_actions)


@pytest.mark.asyncio
async def test_long_names_are_cut(session: NotteSession) -> None:
    _ = await session.window.page.goto(_data_url(f"<button>{'word ' * 200}</button>"))
    _ = await session.aobserve()
    (node,) = session.snapshot.interaction_nodes()
    assert node.accessible_name is not None
    assert len(node.accessible_name) == 200
    assert node.accessible_name.startswith("word word")
