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
