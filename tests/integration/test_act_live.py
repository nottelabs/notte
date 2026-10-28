"""Live tests of `session.act()`, `choose()` and `check()` with the real deciders on real pages (network, model keys).

They assert what the page did (field values, the submitted query, the URL), not what the result reports.

Skipped without keys. `OPENROUTER_API_KEY` (with `NOTTE_LLM_BASE_URL` unset) runs everything: Jev through
OpenRouter's decisions endpoint, the LLM decider and the default field writer. With `TYPESAFE_API_KEY` too, the
`jev` cases call TypeSafe directly instead. Each test prints the per-step
timings and the decision model.
"""

import os
from urllib.parse import parse_qs, quote, urlsplit

import pytest
from notte_core.act import ActResult, Decider, aact_until_done
from notte_core.actions import SelectDropdownOptionAction
from notte_core.dom_tree import NodeSelectors
from notte_core.observation import Observation

import notte

# the default decision and writer models are OpenRouter model ids
_ON_OPENROUTER = urlsplit(os.getenv("NOTTE_LLM_BASE_URL") or "https://openrouter.ai").hostname == "openrouter.ai"
HAS_OPENROUTER = _ON_OPENROUTER and bool(os.getenv("NOTTE_LLM_API_KEY") or os.getenv("OPENROUTER_API_KEY"))

FORM = """<html><head><title>Signup</title></head><body><h1>Newsletter signup</h1>
<form onsubmit="event.preventDefault(); document.getElementById('out').textContent =
  'Thanks ' + document.getElementById('name').value + ' <' + document.getElementById('email').value + '> (' +
  document.getElementById('country').value + ', terms=' + document.getElementById('terms').checked + ')';">
<label>Full name <input id="name" name="name"></label><br>
<label>Email <input id="email" name="email" type="email"></label><br>
<label>Country <select id="country" name="country"><option value="">Choose</option>
  <option value="fr">France</option><option value="us">United States</option></select></label><br>
<label><input type="checkbox" id="terms" name="terms"> I accept the terms</label><br>
<button type="submit">Subscribe</button></form><p id="out"></p></body></html>"""
FORM_GOAL = "Subscribe as Jane Doe with email {{email}} from France, accepting the terms"
FORM_EXPECTED = "Thanks Jane Doe <jane@example.com> (fr, terms=true)"


def _decider(kind: str) -> Decider:
    from notte_llm.act import DEFAULT_ACT_MODEL, DEFAULT_TEXT_MODEL, JevDecider, LlmDecider, LlmWriter  # noqa: PLC0415

    writer = LlmWriter(DEFAULT_TEXT_MODEL, fallback_model=DEFAULT_ACT_MODEL)
    # Jev: TypeSafe directly with TYPESAFE_API_KEY, else through OpenRouter
    return JevDecider(writer=writer) if kind == "jev" else LlmDecider(DEFAULT_ACT_MODEL, writer=writer)


def _report(name: str, results: list[ActResult]) -> None:
    print(f"\n{name}")
    for i, r in enumerate(results):
        t = r.timings
        print(
            f"  {i} {r.status:9s} {r.operation or '':12s} {r.target or '':6s} {r.value or '':22s} "
            + f"observe={t.observe_ms:.0f} decide={t.decide_ms:.0f} write={t.write_ms:.0f} "
            + f"fresh={t.fresh_ms:.0f} execute={t.execute_ms:.0f} total={t.total_ms:.0f} ms ({r.model})"
        )


DECIDERS = [
    pytest.param(
        kind,
        marks=pytest.mark.skipif(
            not HAS_OPENROUTER, reason="needs an OpenRouter key (OPENROUTER_API_KEY, NOTTE_LLM_BASE_URL unset)"
        ),
    )
    for kind in ("jev", "llm")
]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", DECIDERS)
async def test_local_form(kind: str) -> None:
    async with notte.Session(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(FORM)}")
        results = await aact_until_done(
            session, FORM_GOAL, max_steps=8, variables={"email": "jane@example.com"}, decider=_decider(kind)
        )
        _report(f"local form ({kind})", results)
        assert await session.window.page.inner_text("#out") == FORM_EXPECTED
        assert results[-1].status == "done"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", DECIDERS)
async def test_local_public_search(kind: str) -> None:
    async with notte.Session(headless=True) as session:
        _ = await session.aexecute(type="goto", url="https://en.wikipedia.org/wiki/Main_Page")
        results = await aact_until_done(
            session, "Search Wikipedia for Ada Lovelace and open her article", max_steps=6, decider=_decider(kind)
        )
        _report(f"local wikipedia ({kind})", results)
        assert "Ada_Lovelace" in session.window.page.url


WEB_FORM = "https://www.selenium.dev/selenium/web/web-form.html"
# These checks exercise model decisions and live DOM state, not public-site uptime.
DROPDOWN = """<!doctype html><title>Dropdown</title><h1>Dropdown List</h1>
<select id="dropdown"><option value="" disabled selected>Please select an option</option>
<option value="1">Option 1</option><option value="2">Option 2</option></select>"""
CHECKBOXES = """<!doctype html><title>Checkboxes</title><h1>Checkboxes</h1>
<form id="checkboxes"><input type="checkbox"> checkbox 1<br>
<input type="checkbox" checked> checkbox 2</form>"""
ADA = "https://en.wikipedia.org/wiki/Ada_Lovelace"
# the element an xpath points at, by its stable attributes: id, else name, else tag
ELEMENT_JS = """xpath => {
  const el = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
  return el && (el.id || el.getAttribute("name") || el.tagName.toLowerCase());
}"""
# flip both checkboxes, so the answer depends on the live state and not on the page's HTML
FLIP_CHECKBOXES_JS = "document.querySelectorAll('#checkboxes input').forEach(c => c.click())"
CHECKBOX_OPTIONS = {
    "first": "Only the first checkbox is checked",
    "second": "Only the second checkbox is checked",
    "both": "Both checkboxes are checked",
    "none": "No checkbox is checked",
}


def _xpath(observation: Observation, target: str | None) -> str:
    """The xpath of the element `target` (`I1`, or `I1:2` for an option of a select) points at."""
    assert target is not None
    element_id = target.split(":")[0]
    action = next(a for a in observation.space.interaction_actions if a.id == element_id)
    assert isinstance(action.selector, NodeSelectors)
    return action.selector.xpath_selector


async def _local_step(session: notte.Session, instruction: str, decider: Decider, operation: str) -> str:
    """One `act()` step that must execute `operation`; returns the element it acted on (see `ELEMENT_JS`)."""
    observation = await session.aobserve()
    # read before acting: a click may navigate away
    elements = {
        action.id: await session.window.page.evaluate(ELEMENT_JS, _xpath(observation, action.id))
        for action in observation.space.interaction_actions
    }
    result = await session.aact(instruction, observation=observation, decider=decider)
    _report(instruction, [result])
    assert result.status == "executed" and result.operation == operation, result
    assert result.execution is not None and result.execution.success, result.execution
    assert result.target is not None
    return elements[result.target.split(":")[0]]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", DECIDERS)
async def test_local_act_steps_fill_and_submit_a_form(kind: str) -> None:
    decider = _decider(kind)
    async with notte.Session(headless=True) as session:
        page = session.window.page
        _ = await session.aexecute(type="goto", url=WEB_FORM)

        assert await _local_step(session, 'Type "Notte" into the text input', decider, "TYPE_TEXT") == "my-text-id"
        assert await page.input_value("#my-text-id") == "Notte"

        assert await _local_step(session, 'Select "Two" in the select dropdown', decider, "SELECT") == "my-select"
        assert await page.input_value("select[name=my-select]") == "2"

        assert await _local_step(session, 'Check the "Default checkbox"', decider, "CLICK") == "my-check-2"
        assert await page.is_checked("#my-check-2") and await page.is_checked("#my-check-1")

        assert await _local_step(session, "Submit the form", decider, "CLICK") == "button"
        await page.wait_for_url("**/submitted-form.html?*", timeout=15_000)
        submitted = parse_qs(urlsplit(page.url).query)
        assert submitted["my-text"] == ["Notte"]
        assert submitted["my-select"] == ["2"]
        assert submitted["my-check"] == ["on", "on"]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", DECIDERS)
async def test_local_select_picks_the_option(kind: str) -> None:
    async with notte.Session(headless=True) as session:
        url = "https://act-fixture.notte.test/dropdown"
        await session.window.page.route(url, lambda route: route.fulfill(content_type="text/html", body=DROPDOWN))
        _ = await session.window.page.goto(url)
        observation = await session.aobserve()
        result = await session.aact(
            'Select "Option 2" in the dropdown', observation=observation, decider=_decider(kind)
        )
        _report(f"local select ({kind})", [result])
        assert result.status == "executed" and result.operation == "SELECT", result
        assert isinstance(result.action, SelectDropdownOptionAction)
        assert await session.window.page.evaluate(ELEMENT_JS, _xpath(observation, result.target)) == "dropdown"
        assert await session.window.page.input_value("#dropdown") == "2"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", DECIDERS)
async def test_local_choose_a_fact_from_the_page(kind: str) -> None:
    options = ["English", "French", "American"]
    async with notte.Session(headless=True) as session:
        _ = await session.aexecute(type="goto", url=ADA)
        choice = await session.achoose("What was Ada Lovelace's nationality?", options, decider=_decider(kind))
        print(f"\nlocal choose fact ({kind}): {choice}")
        assert choice.choice == "English"
        assert set(choice.probabilities) == set(options)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", DECIDERS)
async def test_local_choose_from_the_live_state(kind: str) -> None:
    async with notte.Session(headless=True) as session:
        # A data URL would expose the stale initial checked attribute to the
        # model alongside the live DOM state after the checkboxes are flipped.
        url = "https://act-fixture.notte.test/checkboxes"
        await session.window.page.route(url, lambda route: route.fulfill(content_type="text/html", body=CHECKBOXES))
        _ = await session.window.page.goto(url)
        await session.window.page.evaluate(FLIP_CHECKBOXES_JS)
        assert await session.window.page.locator("#checkboxes input").evaluate_all(
            "elements => elements.map(element => element.checked)"
        ) == [True, False]
        choice = await session.achoose("Which checkboxes are checked?", CHECKBOX_OPTIONS, decider=_decider(kind))
        print(f"\nlocal choose state ({kind}): {choice}")
        assert choice.choice == "first"
        assert set(choice.probabilities) == set(CHECKBOX_OPTIONS)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", DECIDERS)
async def test_local_check_true_and_false(kind: str) -> None:
    decider = _decider(kind)
    async with notte.Session(headless=True) as session:
        _ = await session.aexecute(type="goto", url=ADA)
        about_ada = await session.acheck("Is this the Wikipedia article about Ada Lovelace?", decider=decider)
        about_turing = await session.acheck("Is this page about Alan Turing?", decider=decider)
        print(f"\nlocal check ({kind}): ada={about_ada:.3f} turing={about_turing:.3f}")
        assert about_ada > 0.5
        assert about_turing < 0.5
