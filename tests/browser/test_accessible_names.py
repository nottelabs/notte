"""`observe()` gives each interaction element its accessible name (`DomNode.accessible_name`, and
`accessible_name` on the actions), as Chromium computes it, without changing the descriptions."""

from collections.abc import AsyncIterator
from urllib.parse import quote

import pytest
import pytest_asyncio
from notte_browser.dom.parsing import DOM_TREE_JS
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
<label for="labelledsubmit">Confirm purchase</label> <input id="labelledsubmit" type="submit" value="Send">
<button id="linebreak">Place<br>order</button>
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
    "labelledsubmit": "Confirm purchase",
    "linebreak": "Place order",
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


@pytest.mark.asyncio
async def test_formatting_whitespace_does_not_cut_names(session: NotteSession) -> None:
    _ = await session.window.page.goto(_data_url(f"<button>{' ' * 2000}<span>Save</span></button>"))
    _ = await session.aobserve()
    (node,) = session.snapshot.interaction_nodes()
    assert node.accessible_name == "Save"


LISTBOX_BUTTONS = """
<span id="speed-label">Shipping speed</span>
<button id="speed" aria-haspopup="listbox" aria-expanded="false" aria-labelledby="speed-label speed">
  Standard (5-7 days)
</button>
<ul role="listbox" aria-labelledby="speed-label" hidden><li role="option" aria-selected="true">Standard</li></ul>
<button id="size" aria-haspopup="listbox" aria-labelledby="size">Medium</button>
<span id="delete-label">section 2</span>
<button id="delete" aria-labelledby="delete delete-label">Delete</button>
"""


@pytest.mark.asyncio
async def test_a_listbox_button_shows_its_selected_option_as_its_value() -> None:
    # the collapsible listbox pattern labels its button by the label and by the button, whose text is the
    # selected option: "Shipping speed Standard (5-7 days)" was one name, with no value to tell them apart
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(_data_url(LISTBOX_BUTTONS))
        _ = await session.aobserve()
        nodes = _nodes_by_html_id(session)

    speed = nodes["speed"]
    assert speed.accessible_name == "Shipping speed"
    assert speed.state is not None and speed.state.value == "Standard (5-7 days)"
    # labelled by itself alone, its text is its name
    assert nodes["size"].accessible_name == "Medium"
    # a button that does not open a listbox is named as browsers do
    assert nodes["delete"].accessible_name == "Delete section 2"
    assert nodes["delete"].state is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "control",
    [
        'a href="#next"',
        "button",
        'div role="button" tabindex="0"',
        'a href="#next" role="button"',
        'form role="button" tabindex="0"',
    ],
)
async def test_listbox_value_rule_requires_a_button(control: str) -> None:
    """Only native and semantic buttons split the label from the selected value."""
    tag = control.split()[0]
    fields = '<input type="hidden" name="children"><input type="hidden" name="childNodes">' if tag == "form" else ""
    html = f'<span id="label">Shipping speed</span><{control} id="choice" aria-haspopup="listbox" aria-labelledby="label choice">Standard{fields}</{tag}>'
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(_data_url(html))
        _ = await session.aobserve()
        choice = _nodes_by_html_id(session)["choice"]
    if control == 'a href="#next"':
        assert choice.accessible_name == "Shipping speed Standard"
        assert choice.state is None
    else:
        assert choice.accessible_name == "Shipping speed"
        assert choice.state is not None and choice.state.value == "Standard"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "selection",
    [
        '<span aria-label="Selected option">Standard</span>',
        '<span aria-labelledby="other">Standard</span><span hidden id="other">Selected option</span>',
        '<span>  Stan</span><span>dard</span><br><span style="text-transform: uppercase"> delivery </span>',
        "<span>Standard</span><svg><title>Open dropdown</title></svg>",
        '<svg width="160" height="30"><text x="0" y="20">Standard</text></svg>',
        '<svg width="160" height="30"><title>Open dropdown</title><desc>Decorative icon</desc>'
        "<metadata>Chart metadata</metadata><defs><text>Unused template</text></defs>"
        '<text x="0" y="20"><tspan>Standard</tspan></text></svg>',
    ],
)
async def test_listbox_value_reads_visible_text_instead_of_descendant_names(selection: str) -> None:
    """Selection text ignores descendant names and icon metadata without changing name semantics."""
    html = f'<span id="label">Shipping speed</span><button id="choice" aria-haspopup="listbox" aria-labelledby="label choice">{selection}</button><button id="ordinary"><span aria-label="Selected option">Standard</span></button>'
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(_data_url(html))
        _ = await session.aobserve()
        nodes = _nodes_by_html_id(session)
    assert nodes["choice"].accessible_name == "Shipping speed"
    state = nodes["choice"].state
    assert state is not None
    assert state.value == ("Standard DELIVERY" if "text-transform" in selection else "Standard")
    assert nodes["ordinary"].accessible_name == "Selected option"


@pytest.mark.asyncio
@pytest.mark.parametrize("input_type", ["button", "submit", "reset"])
async def test_input_listbox_button_keeps_its_live_selection(input_type: str) -> None:
    html = f"""
    <span id="speed-label">Shipping speed</span>
    <input type="{input_type}" id="speed" value="Standard"
           aria-haspopup="listbox" aria-labelledby="speed-label speed">
    <input type="button" id="plain" value="Save">
    """
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(_data_url(html))
        _ = await session.aobserve()
        nodes = _nodes_by_html_id(session)
        speed = nodes["speed"]
        assert speed.accessible_name == "Shipping speed"
        assert speed.state is not None and speed.state.value == "Standard"
        assert nodes["plain"].accessible_name == "Save"
        assert nodes["plain"].state is None

        await session.window.page.locator("#speed").evaluate("element => element.value = 'Express'")
        _ = await session.aobserve()
        speed = _nodes_by_html_id(session)["speed"]
        assert speed.accessible_name == "Shipping speed"
        assert speed.state is not None and speed.state.value == "Express"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "hidden_content",
    [
        '<svg aria-hidden="true"><title>Open dropdown</title></svg>',
        "<span hidden>Previous selection</span>",
        '<span style="visibility: hidden">Previous selection</span>',
    ],
)
async def test_listbox_button_value_excludes_hidden_content(hidden_content: str) -> None:
    html = f"""
    <span id="speed-label">Shipping speed</span>
    <button id="speed" aria-haspopup="listbox" aria-labelledby="speed-label speed">
      Standard (5-7 days){hidden_content}
    </button>
    """
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(_data_url(html))
        _ = await session.aobserve()
        speed = _nodes_by_html_id(session)["speed"]

    assert speed.accessible_name == "Shipping speed"
    assert speed.state is not None and speed.state.value == "Standard (5-7 days)"


@pytest.mark.asyncio
@pytest.mark.parametrize("nested", [False, True])
async def test_listbox_button_value_follows_slotted_selection(nested: bool) -> None:
    html = """
    <div id="host"><span slot="selected" aria-label="Selected option">Standard (5-7 days)<span hidden>Old choice</span></span></div>
    <script>
      document.getElementById("host").attachShadow({mode: "open"}).innerHTML = `
        <style>button { width: 400px; text-align: left; }</style>
        <span id="speed-label">Shipping speed</span>
        <button id="speed" aria-haspopup="listbox" aria-labelledby="speed-label speed">
          <slot name="selected"><span aria-label="Placeholder">Choose a speed</span></slot>
        </button>`;
    </script>
    """
    if nested:
        html = html.replace('<slot name="selected">', '<slot><slot name="selected">').replace(
            "</span></slot>", "</span></slot></slot>"
        )
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(_data_url(html))
        _ = await session.aobserve()
        speed = _nodes_by_html_id(session)["speed"]
        assert speed.accessible_name == "Shipping speed"
        assert speed.state is not None and speed.state.value == "Standard (5-7 days)"

        _ = await session.window.page.evaluate("document.querySelector('[slot=selected]').remove()")
        _ = await session.aobserve()
        speed = _nodes_by_html_id(session)["speed"]
        assert speed.accessible_name == "Shipping speed"
        assert speed.state is not None and speed.state.value == "Choose a speed"


def _value_digest(value: str) -> str:
    """The state contract hashes the normalized UTF-16 code units read with FNV-1a."""
    hashed = 0xCBF29CE484222325
    encoded = value.encode("utf-16-le")
    for index in range(0, len(encoded), 2):
        hashed = ((hashed ^ int.from_bytes(encoded[index : index + 2], "little")) * 0x100000001B3) & ((1 << 64) - 1)
    return f"{hashed:016x}"


@pytest.mark.asyncio
async def test_listbox_selection_hashes_the_full_normalized_value() -> None:
    """Within the traversal budget, suffix edits beyond display/name limits change the full digest."""
    html = '<span id="label">Shipping speed</span><button style="width: 400px; overflow-wrap: anywhere" id="choice" aria-haspopup="listbox" aria-labelledby="label choice"></button>'
    async with NotteSession(headless=True) as session:
        page = session.window.page
        _ = await page.goto(_data_url(html))
        digests: list[str | None] = []
        for suffix in ["first", "second", "second"]:
            await page.locator("#choice").evaluate(
                "(el, suffix) => { el.replaceChildren(document.createTextNode('  ' + 'x'.repeat(1200)), Object.assign(document.createElement('span'), {textContent: '\\n 🚚 ' + suffix + '  '})); }",
                suffix,
            )
            _ = await session.aobserve()
            state = _nodes_by_html_id(session)["choice"].state
            assert state is not None and state.value == "x" * 200 and state.value_truncated
            assert state.value_digest == _value_digest("x" * 1200 + " 🚚 " + suffix)
            digests.append(state.value_digest)
        assert digests[0] != digests[1] == digests[2]


@pytest.mark.asyncio
@pytest.mark.parametrize("references", [0, 5000])
async def test_listbox_value_does_not_expand_aria_graphs_or_materialize_the_selection(references: int) -> None:
    """Enforce deterministic work/output budgets on the value reader, apart from the DOM build."""
    html = '<span id="label">Shipping speed</span><button id="choice" aria-haspopup="listbox" aria-labelledby="label choice"></button><span id="external" hidden>Outside selection</span>'
    # Exercise the actual reader in its browser context, without charging the unrelated tree build.
    probe = DOM_TREE_JS.replace(
        "const rootId = buildDomTree(BODY);",
        """
        const originalReplace = String.prototype.replace;
        const originalGetAttribute = Element.prototype.getAttribute;
        let reads = 0;
        String.prototype.replace = function (...args) {
            if (this.length > 1024) throw new Error('materialized selection exceeds string-work budget');
            return originalReplace.apply(this, args);
        };
        Element.prototype.getAttribute = function (...args) {
            if (++reads > 1000) throw new Error('repeated references exceed DOM-work budget');
            return originalGetAttribute.apply(this, args);
        };
        try { return getLiveState(document.querySelector('#choice')); }
        finally {
            String.prototype.replace = originalReplace;
            Element.prototype.getAttribute = originalGetAttribute;
        }
    """,
    )
    async with NotteSession(headless=True) as session:
        page = session.window.page
        _ = await page.goto(_data_url(html))
        await page.locator("#choice").evaluate(
            """(el, references) => {
            const span = document.createElement('span');
            if (references) span.setAttribute('aria-labelledby', 'external '.repeat(references));
            span.textContent = 'x'.repeat(200000) + 'tail';
            el.append(span);
        }""",
            references,
        )
        args = {
            "highlight_elements": False,
            "focus_element": -1,
            "viewport_expansion": 0,
            "enable_pointer_elements": True,
        }
        for suffix in ["tail", "edit"]:
            await page.locator("#choice span").evaluate(
                "(el, suffix) => el.firstChild.replaceData(200000, 4, suffix)", suffix
            )
            state = await page.evaluate(probe, args, isolated_context=False)
            assert state == {
                "value": "x" * 200,
                "valueTruncated": True,
                # The authorized traversal cutoff makes edits past the read prefix intentionally partial.
                "valueDigest": _value_digest("x" * 4096),
            }


@pytest.mark.asyncio
@pytest.mark.parametrize("shape", ["wide", "deep", "whitespace", "transformed"])
async def test_listbox_value_stops_at_fixed_node_and_text_budgets(shape: str) -> None:
    """Large/deep selections stop deterministic work, and suffix edits past the cutoff are partial."""
    node_type_anchor = 'const nodeTypeOf = nativeGetter(Node.prototype, "nodeType");'
    assert node_type_anchor in DOM_TREE_JS, "node-work budget probe anchor not found"
    probe = DOM_TREE_JS.replace(
        "const rootId = buildDomTree(BODY);",
        """
        const choice = document.querySelector('#choice');
        const state = {};
        state.value = readListboxValue(choice, state);
        return state;
        """,
    ).replace(
        node_type_anchor,
        """
        const nativeNodeType = nativeGetter(Node.prototype, "nodeType");
        let nodeReads = 0;
        const nodeTypeOf = (node) => {
            if (++nodeReads > 2048) throw new Error('selection exceeded node-work budget');
            return nativeNodeType(node);
        };
        """,
    )
    async with NotteSession(headless=True) as session:
        page = session.window.page
        _ = await page.goto(_data_url('<button id="choice"></button>'))
        await page.locator("#choice").evaluate(
            """(el, shape) => {
                let parent = el;
                for (let i = 0; i < (shape === 'wide' || shape === 'deep' ? 5000 : 1); i++) {
                    const node = document.createElement('span');
                    if (shape === 'transformed') node.style.textTransform = 'uppercase';
                    node.append(document.createTextNode(shape === 'deep' ? '' :
                        shape === 'whitespace' ? ' '.repeat(200000) :
                        shape === 'transformed' ? 'x'.repeat(200000) : 'x'));
                    parent.append(node);
                    if (shape === 'deep') parent = node;
                }
                parent.append(Object.assign(document.createElement('i'), {id: 'tail', textContent: 'first'}));
            }""",
            shape,
        )
        states = []
        for suffix in ["first", "second"]:
            await page.locator("#tail").evaluate("(el, text) => el.textContent = text", suffix)
            states.append(await page.evaluate(probe, {}, isolated_context=False))
        assert states[0] == states[1]
        assert states[0]["valueTruncated"] is True
        expected = {"wide": "x" * 512, "deep": "", "whitespace": "", "transformed": "X" * 4096}[shape]
        assert states[0]["value"] == expected[:200]
        assert states[0]["valueDigest"] == _value_digest(expected)
