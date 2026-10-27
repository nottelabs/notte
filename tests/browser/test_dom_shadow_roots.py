"""Actions reach the controls at the top of an open shadow root.

The XPath of a direct child of a shadow root was empty: the script left out the element's own step, not
only its parent's path. Its CSS path was then made of its attributes alone, which matches the same control
in every instance of a web component (`<input id="i">` in each field), and the XPath through the shadow
roots ended with an empty `xpath=`, which Playwright rejects. The action failed with "The string '' is not
a valid XPath expression". Elements now have their own step, and the CSS path of an element in a shadow
root goes on from its host's (Playwright's CSS engine enters open shadow roots; its XPath engine does not).
"""

from urllib.parse import quote

import pytest
from notte_browser.session import NotteSession

PAGE = """
<my-form></my-form>
<script>
  class MyField extends HTMLElement {
    connectedCallback() {
      this.attachShadow({ mode: "open" }).innerHTML =
        `<label for="i">${this.getAttribute("label")}</label><input id="i">`;
    }
  }
  class MyForm extends HTMLElement {
    connectedCallback() {
      this.attachShadow({ mode: "open" }).innerHTML = `
        <my-field label="Name"></my-field><my-field label="Email"></my-field>
        <button type="button" onclick="document.title = 'sent'">Send</button>`;
    }
  }
  customElements.define("my-field", MyField);
  customElements.define("my-form", MyForm);
</script>
"""

FIELD_VALUES = """() => Array.from(
    document.querySelector("my-form").shadowRoot.querySelectorAll("my-field"),
    (field) => field.shadowRoot.querySelector("input").value,
)"""


@pytest.mark.asyncio
async def test_controls_at_the_top_of_shadow_roots_can_be_used() -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(PAGE)}")
        obs = await session.aobserve()
        fields = [action for action in obs.space.interaction_actions if action.id.startswith("I")]
        send = next(action for action in obs.space.interaction_actions if action.text_label == "Send")
        assert len(fields) == 2

        for field, value in zip(fields, ["Ada", "ada@example.test"]):
            result = await session.aexecute(type="fill", id=field.id, value=value)
            assert result.success, result.message
        assert await session.window.page.evaluate(FIELD_VALUES) == ["Ada", "ada@example.test"]

        result = await session.aexecute(type="click", id=send.id)
        assert result.success, result.message
        assert await session.window.page.title() == "sent"


@pytest.mark.asyncio
async def test_selectors_of_elements_in_shadow_roots() -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(PAGE)}")
        _ = await session.aobserve()
        selectors = [
            (node.computed_attributes.selectors.xpath_selector, node.computed_attributes.selectors.css_selector)
            for node in session.snapshot.dom_node.flatten()
            if node.computed_attributes.selectors is not None and node.computed_attributes.selectors.in_shadow_root
        ]
        # XPaths restart at each shadow root, with the element's own step (and its position there)
        assert selectors == [
            ("html/body/my-form", "html > body > my-form"),
            ("my-field[1]", "html > body > my-form > my-field:nth-of-type(1)"),
            ("label", 'html > body > my-form > my-field:nth-of-type(1) > label[for="i"]'),
            ("input", 'html > body > my-form > my-field:nth-of-type(1) > input[id="i"]'),
            ("my-field[2]", "html > body > my-form > my-field:nth-of-type(2)"),
            ("label", 'html > body > my-form > my-field:nth-of-type(2) > label[for="i"]'),
            ("input", 'html > body > my-form > my-field:nth-of-type(2) > input[id="i"]'),
            ("button", 'html > body > my-form > button[type="button"]'),
        ]


def _same_tag_page(wrap: str, inner: str) -> str:
    """A host with a light child and a shadow child of the same tag: they have the same CSS path, and Playwright's
    XPath engine, which does not enter shadow roots, finds the light one from the host."""
    light = inner.format(label="Light", title="light")
    shadow = inner.format(label="Shadow", title="shadow").replace('"', '\\"')
    return (
        wrap.format(host=f"<x-box>{light}</x-box>")
        + f"""
<script>
  document.querySelector("x-box").attachShadow({{ mode: "open" }}).innerHTML = "{shadow}<slot></slot>";
</script>"""
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("wrap", ["{host}", "<div><p>Box</p>{host}</div>"])
@pytest.mark.parametrize(
    "inner",
    [
        "<button onclick=\"document.title = '{title}'\">{label}</button>",
        "<div><button onclick=\"document.title = '{title}'\">{label}</button></div>",
    ],
)
async def test_a_shadow_child_and_a_light_child_with_the_same_path_are_told_apart(wrap: str, inner: str) -> None:
    async with NotteSession(headless=True) as session:
        page = session.window.page
        _ = await page.goto(f"data:text/html,{quote(_same_tag_page(wrap, inner))}")
        obs = await session.aobserve()
        buttons = {action.text_label: action.id for action in obs.space.interaction_actions}
        assert sorted(buttons) == ["Light", "Shadow"]

        for label, action_id in buttons.items():
            _ = await page.evaluate("document.title = ''")
            result = await session.aexecute(type="click", id=action_id)
            assert result.success, result.message
            assert await page.title() == label.lower()


@pytest.mark.asyncio
async def test_a_removed_shadow_child_is_not_replaced_by_the_light_child() -> None:
    """When the observed shadow child is gone, its CSS path matches only the light child: the click fails."""
    page_html = _same_tag_page("{host}", "<button onclick=\"document.title = '{title}'\">{label}</button>")
    async with NotteSession(headless=True) as session:
        page = session.window.page
        _ = await page.goto(f"data:text/html,{quote(page_html)}")
        obs = await session.aobserve()
        shadow = next(action for action in obs.space.interaction_actions if action.text_label == "Shadow")

        _ = await page.evaluate("document.querySelector('x-box').shadowRoot.querySelector('button').remove()")
        result = await session.aexecute(type="click", id=shadow.id, raise_on_failure=False)
        assert not result.success
        assert await page.title() == ""


HOST_SCRIPT = """<script>
  for (const host of document.querySelectorAll("[data-host]")) {
    host.attachShadow({ mode: "open" }).innerHTML = "<span>Open</span><slot></slot>";
  }
</script>"""
HOST = '<x-box role="button" data-host onclick="document.title = \'host\'"></x-box>'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        HOST,
        # a light sibling of the same tag
        HOST + '<x-box role="button" onclick="document.title = \'sibling\'">Other</x-box>',
    ],
)
async def test_a_shadow_host_can_be_clicked(body: str) -> None:
    """A host is not in its own shadow root: its CSS path is what finds it."""
    async with NotteSession(headless=True) as session:
        page = session.window.page
        _ = await page.goto(f"data:text/html,{quote(body + HOST_SCRIPT)}")
        obs = await session.aobserve()
        host = next(action for action in obs.space.interaction_actions if action.text_label == "Open")

        result = await session.aexecute(type="click", id=host.id)
        assert result.success, result.message
        assert await page.title() == "host"


@pytest.mark.asyncio
async def test_a_shadow_host_in_a_shadow_root_can_be_clicked() -> None:
    page_html = """<x-outer></x-outer>
<script>
  const root = document.querySelector("x-outer").attachShadow({ mode: "open" });
  root.innerHTML = `<x-box role="button" onclick="document.title = 'host'"></x-box>`;
  root.querySelector("x-box").attachShadow({ mode: "open" }).innerHTML = "<span>Open</span>";
</script>"""
    async with NotteSession(headless=True) as session:
        page = session.window.page
        _ = await page.goto(f"data:text/html,{quote(page_html)}")
        obs = await session.aobserve()
        host = next(action for action in obs.space.interaction_actions if action.text_label == "Open")

        result = await session.aexecute(type="click", id=host.id)
        assert result.success, result.message
        assert await page.title() == "host"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("light", "shadow"),
    [
        # the inner host and the button in its shadow root both have the XPath `x-box`
        ("", """<x-box role="button" onclick="document.title = 'inner'">Open</x-box>"""),
        # the button in the inner host's shadow root has the XPath `x-box/button`, which also reads as a light child
        # of the host, where a button is
        (
            """<button onclick="document.title = 'light'">Light</button>""",
            """<x-box><button onclick="document.title = 'inner'">Open</button></x-box><slot></slot>""",
        ),
    ],
)
async def test_a_shadow_child_with_the_path_of_its_host_can_be_clicked(light: str, shadow: str) -> None:
    page_html = f"""<x-outer></x-outer>
<script>
  const root = document.querySelector("x-outer").attachShadow({{ mode: "open" }});
  root.innerHTML = `<x-box>{light}</x-box>`;
  root.querySelector("x-box").attachShadow({{ mode: "open" }}).innerHTML = `{shadow}`;
</script>"""
    async with NotteSession(headless=True) as session:
        page = session.window.page
        _ = await page.goto(f"data:text/html,{quote(page_html)}")
        obs = await session.aobserve()
        button = next(action for action in obs.space.interaction_actions if action.text_label == "Open")

        result = await session.aexecute(type="click", id=button.id)
        assert result.success, result.message
        assert await page.title() == "inner"
