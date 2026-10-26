# pyright: basic
"""Public sites, round 3: masked inputs (Cleave.js, imask), number steppers (Element Plus on Vue, Ant Design on React),
an ARIA toolbar with a spinbutton (W3C APG), a field enabled after a delay (UI Testing Playground), client-side routing
on SvelteKit (Svelte Hacker News), VitePress (Element Plus) and Next.js (its docs), infinite scroll and pagination
(quotes.toscrape.com, books.toscrape.com), and Spanish, German and French news sites behind cookie walls (El País,
RTVE, heise in a cross-origin consent frame, Le Figaro with no reject button), and Spanish Wikipedia."""

import json
from dataclasses import replace
from typing import Any
from urllib.parse import unquote

from ..model import REAL_MAX_STEPS, Probe, Task, ci_tier, path
from .cov2_real import _onetrust_refused  # pyright: ignore[reportPrivateUsage]


def _extra(f: dict[str, Any]) -> Any:
    return f.get("extra")


def _value(selector: str) -> str:
    """The value of the first visible element matching `selector` (pages repeat widgets in hidden demos)."""
    return (
        f"JSON.stringify(([...document.querySelectorAll({json.dumps(selector)})].find(e => "
        "e.getBoundingClientRect().width > 0) || {}).value ?? null)"
    )


def _attr(selector: str, attribute: str) -> str:
    return (
        f"JSON.stringify((e => e && e.getBoundingClientRect().width > 0 ? e.getAttribute({json.dumps(attribute)}) : null)"
        f"(document.querySelector({json.dumps(selector)})))"
    )


def _path_is(expected: str):
    def check(f: dict[str, Any], _: dict[str, Any]) -> bool:
        return unquote(path(f)).rstrip("/") == expected.rstrip("/")

    return check


def _path_starts(prefix: str):
    def check(f: dict[str, Any], _: dict[str, Any]) -> bool:
        return path(f).startswith(prefix)

    return check


# Pablo Neruda's quote (on the third page of the scroll) is on screen, even cut by an edge of the viewport
NERUDA_IN_VIEW = """JSON.stringify((q => q ? (r => r.bottom > 0 && r.top < innerHeight)(q.getBoundingClientRect()) : false)(
  [...document.querySelectorAll('.quote')].find(q => (q.querySelector('.author') || {}).innerText === 'Pablo Neruda')))"""

CLEAVE = "https://nosir.github.io/cleave.js/"
IMASK = "https://imask.js.org/"
EP_NUMBER = "https://element-plus.org/en-US/component/input-number.html"
ANT_NUMBER = "https://ant.design/components/input-number"
TOOLBAR = "https://www.w3.org/WAI/ARIA/apg/patterns/toolbar/examples/toolbar/"
QUOTES = "http://quotes.toscrape.com"

TASKS = [
    # ---- masked inputs and number steppers
    Task(
        "cleave-card",
        CLEAVE,
        "Type the credit card number 4111111111111111 in the credit card field.",
        lambda f, _: _extra(f) == "4111 1111 1111 1111",
        final_js=_value(".input-credit-card"),
        tags=("masked-input",),
    ),
    Task(
        "cleave-date",
        CLEAVE,
        "Enter the date 15 November 2026 in the YYYY-MM-DD date field.",
        lambda f, _: _extra(f) == "2026-11-15",
        final_js=_value(".input-date-a"),
        tags=("masked-input", "date"),
    ),
    Task(
        "imask-phone",
        IMASK,
        "Enter the phone number 912 345 67 89 in the phone field.",
        lambda f, _: _extra(f) == "+7(912)345-67-89",
        final_js=_value("#phone-mask"),
        tags=("masked-input", "phone"),
    ),
    Task(
        "imask-date",
        IMASK,
        "Enter the date 15 March 2005 in the date field.",
        lambda f, _: _extra(f) == "15.03.2005",
        final_js=_value("#date-mask"),
        tags=("masked-input", "date"),
    ),
    Task(
        "ep-stepper",
        EP_NUMBER,
        "Set the first number input of the page to 5.",
        lambda f, _: _extra(f) == "5",
        final_js=_value(".el-input-number input"),
        tags=("stepper", "vue"),
    ),
    Task(
        "ant-stepper",
        ANT_NUMBER,
        "Set the first number input of the page to 10.",
        lambda f, _: _extra(f) == "10",
        final_js=_value(".ant-input-number input"),
        tags=("stepper", "react"),
    ),
    Task(
        "apg-toolbar-bold",
        TOOLBAR,
        "In the example toolbar, make the text bold.",
        lambda f, _: _extra(f) == "true",
        final_js=_attr("[role=toolbar] .bold", "aria-pressed"),
        tags=("toolbar", "toggle-button", "a11y"),
    ),
    Task(
        "apg-toolbar-size",
        TOOLBAR,
        "In the example toolbar, set the font size to 18 points.",
        lambda f, _: _extra(f) == "18",
        final_js=_attr("[role=toolbar] [role=spinbutton]", "aria-valuenow"),
        tags=("toolbar", "spinbutton", "stepper"),
    ),
    Task(
        "uitap-disabled",
        "http://uitestingplayground.com/disabledinput",
        "Enable the edit field, then type notte in it.",
        lambda f, _: _extra(f) == "notte",
        final_js=_value("#inputField"),
        tags=("disabled", "wait"),
    ),
    # ---- client-side routing
    Task(
        "hn-svelte-new",
        "https://hn.svelte.dev/",
        "Show the newest stories, then go to their second page.",
        _path_is("/new/2"),
        tags=("spa", "svelte", "client-routing", "pagination"),
    ),
    Task(
        "ep-sidebar",
        "https://element-plus.org/en-US/component/overview.html",
        "From the sidebar, open the Input Number component page.",
        lambda f, _: path(f).removesuffix(".html") == "/en-US/component/input-number",
        tags=("spa", "vue", "client-routing", "sidebar"),
    ),
    Task(
        "nextjs-docs",
        "https://nextjs.org/docs",
        "From the docs sidebar, open the page about linking and navigating.",
        _path_is("/docs/app/getting-started/linking-and-navigating"),
        tags=("spa", "next", "client-routing", "sidebar"),
    ),
    # ---- infinite scroll and pagination
    Task(
        "quotes-scroll",
        f"{QUOTES}/scroll",
        "Scroll down until the quote by Pablo Neruda is on screen. More quotes load as you scroll.",
        lambda f, _: _extra(f) is True,
        final_js=NERUDA_IN_VIEW,
        tags=("infinite-scroll",),
    ),
    Task(
        "quotes-js-page",
        f"{QUOTES}/js/",
        "Go to the third page of the quotes.",
        _path_is("/js/page/3"),
        tags=("pagination", "js-rendered"),
    ),
    Task(
        "books-mystery-page",
        "http://books.toscrape.com/",
        "Open the Mystery category, then go to its second page.",
        _path_is("/catalogue/category/books/mystery_3/page-2.html"),
        tags=("pagination", "category"),
    ),
    # ---- non-English pages behind cookie walls
    Task(
        "elpais-deportes",
        "https://elpais.com/",
        "Abre la sección de Deportes.",
        _path_starts("/deportes"),
        tags=("es", "consent", "pay-or-ok"),
    ),
    Task(
        "rtve-reject",
        "https://www.rtve.es/",
        "Rechaza todas las cookies y abre las últimas noticias.",
        lambda f, r: _path_is("/noticias/ultimas-noticias")(f, r) and _onetrust_refused(f, r),
        final_js="JSON.stringify(document.cookie)",
        tags=("es", "consent"),
    ),
    Task(
        "heise-newsticker",
        "https://www.heise.de/",
        "Öffne den Newsticker.",
        _path_is("/newsticker"),
        tags=("de", "consent", "iframe", "cross-origin"),
    ),
    Task(
        "lefigaro-economie",
        "https://www.lefigaro.fr/",
        "Ouvre la rubrique Économie.",
        _path_starts("/economie"),
        tags=("fr", "consent", "dark-pattern"),
    ),
    Task(
        "es-wiki",
        "https://es.wikipedia.org/wiki/",
        "Busca «Torre Eiffel» en Wikipedia y abre su artículo.",
        _path_is("/wiki/Torre_Eiffel"),
        tags=("es", "search"),
    ),
]
TASKS = [replace(t, max_steps=REAL_MAX_STEPS) for t in TASKS]

PROBES = [
    Probe("cleave-card-empty", CLEAVE, "Is the credit card number field empty?", None, "YES"),
    Probe(
        "imask-date-range",
        IMASK,
        "Which dates does the date field accept?",
        ["From 01.01.1990 to 01.01.2020", "Any date", "From 01.01.2000 to 31.12.2030", "Only today's date"],
        "From 01.01.1990 to 01.01.2020",
    ),
    Probe("ep-first-value", EP_NUMBER, "What is the value of the first number input?", ["1", "5", "0", "10"], "1"),
    Probe("ep-disabled", EP_NUMBER, "Does the page show a disabled number input?", None, "YES"),
    Probe("ant-first-value", ANT_NUMBER, "What value does the first number input show?", ["3", "1", "10", "0"], "3"),
    Probe("apg-toolbar-bold-on", TOOLBAR, "Is Bold turned on in the example toolbar?", None, "NO"),
    Probe(
        "apg-toolbar-size-now",
        TOOLBAR,
        "What font size does the example toolbar show?",
        ["14 Point", "12 Point", "16 Point", "18 Point"],
        "14 Point",
    ),
    Probe(
        "apg-toolbar-align",
        TOOLBAR,
        "Which text alignment is selected in the example toolbar?",
        ["Left", "Center", "Right", "None"],
        "Left",
    ),
    Probe(
        "uitap-disabled-field", "http://uitestingplayground.com/disabledinput", "Is the edit field enabled?", None, "NO"
    ),
    Probe("hn-svelte-more", "https://hn.svelte.dev/", "Is there a link to more stories?", None, "YES"),
    Probe(
        "nextjs-linking",
        "https://nextjs.org/docs",
        "Does the docs sidebar have a page about linking and navigating?",
        None,
        "YES",
    ),
    Probe(
        "quotes-scroll-first",
        f"{QUOTES}/scroll",
        "Who is the author of the first quote?",
        ["Albert Einstein", "Pablo Neruda", "Jane Austen", "Mark Twain"],
        "Albert Einstein",
    ),
    Probe("quotes-js-next", f"{QUOTES}/js/", "Is there a link to the next page of quotes?", None, "YES"),
    Probe(
        "books-page2-first",
        "http://books.toscrape.com/catalogue/page-2.html",
        "Which book is listed first on this page?",
        ["In Her Wake", "A Light in the Attic", "How Music Works", "Tipping the Velvet"],
        "In Her Wake",
    ),
    Probe("elpais-wall", "https://elpais.com/", "Is a cookie consent dialog shown?", None, "YES"),
    Probe("heise-wall", "https://www.heise.de/", "Is a cookie consent dialog shown?", None, "YES"),
    Probe(
        "lefigaro-refuse",
        "https://www.lefigaro.fr/",
        # the consent dialog (a frame over the page) has "Continue without accepting"
        "Does the cookie consent dialog let you continue without accepting cookies?",
        None,
        "YES",
    ),
    Probe(
        "rtve-reject-button",
        "https://www.rtve.es/",
        "Does the cookie banner have a button to reject all cookies?",
        None,
        "YES",
    ),
    Probe(
        "es-wiki-city",
        "https://es.wikipedia.org/wiki/Torre_Eiffel",
        "In which city is this tower?",
        ["Paris", "Madrid", "Lyon", "Brussels"],
        "Paris",
    ),
]

# Core: W3C APG, UI Testing Playground, quotes.toscrape.com, books.toscrape.com and Wikipedia (very stable demos).
# Extended: library and framework sites (Cleave.js, imask, Element Plus, Ant Design, Next.js, Svelte HN: their pages and
# ads change), the news sites (cookie walls that come late or not at all: bench bug 25; content and A/B tests change
# daily), and until their fixes are on main apg-toolbar-size (bug 23: an ARIA spinbutton takes no value) and the
# apg-toolbar-bold-on probe (bug 24: a toggle outside the viewport loses its pressed state).
TASKS = ci_tier(
    TASKS,
    core={"apg-toolbar-bold", "uitap-disabled", "quotes-scroll", "quotes-js-page", "books-mystery-page", "es-wiki"},
)
PROBES = ci_tier(
    PROBES,
    core={
        "apg-toolbar-size-now",
        "apg-toolbar-align",
        "uitap-disabled-field",
        "quotes-scroll-first",
        "quotes-js-next",
        "books-page2-first",
        "es-wiki-city",
    },
)
