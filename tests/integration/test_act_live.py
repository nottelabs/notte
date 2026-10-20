"""Live smoke tests of `session.act()` with the real deciders (network, model keys).

Skipped without keys: `TYPESAFE_API_KEY` (Jev), `OPENROUTER_API_KEY` (LLM decider and the default
field writer, on the OpenRouter endpoint: `NOTTE_LLM_BASE_URL` unset), `NOTTE_API_KEY` (cloud session).
Each test prints the per-step timings.
"""

import os
from urllib.parse import quote, urlsplit

import pytest
from notte_core.act import ActResult, Decider, aact_until_done, act_until_done
from notte_sdk import NotteClient

import notte

# the default decision and writer models are OpenRouter model ids
_ON_OPENROUTER = urlsplit(os.getenv("NOTTE_LLM_BASE_URL") or "https://openrouter.ai").hostname == "openrouter.ai"
HAS_OPENROUTER = _ON_OPENROUTER and bool(os.getenv("NOTTE_LLM_API_KEY") or os.getenv("OPENROUTER_API_KEY"))
HAS_TYPESAFE = bool(os.getenv("TYPESAFE_API_KEY")) and HAS_OPENROUTER
HAS_NOTTE = bool(os.getenv("NOTTE_API_KEY"))

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
        "jev", marks=pytest.mark.skipif(not HAS_TYPESAFE, reason="needs TYPESAFE_API_KEY and an OpenRouter key")
    ),
    pytest.param(
        "llm",
        marks=pytest.mark.skipif(
            not HAS_OPENROUTER, reason="needs an OpenRouter key (OPENROUTER_API_KEY, NOTTE_LLM_BASE_URL unset)"
        ),
    ),
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


@pytest.mark.skipif(not HAS_NOTTE, reason="needs NOTTE_API_KEY")
@pytest.mark.parametrize("kind", DECIDERS)
def test_cloud_public_search(kind: str) -> None:
    with NotteClient().Session() as session:
        _ = session.execute(type="goto", url="https://en.wikipedia.org/wiki/Main_Page")
        results = act_until_done(
            session, "Search Wikipedia for Ada Lovelace and open her article", max_steps=6, decider=_decider(kind)
        )
        _report(f"cloud wikipedia ({kind})", results)
        assert session.check("Is this the Wikipedia article about Ada Lovelace?", decider=_decider(kind)) > 0.5
