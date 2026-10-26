# pyright: basic
"""Public sites, round 2: sliders (a range input, a noUiSlider), a sortable list (drag and drop: a clean BLOCKED
passes), a file picker, rich editors (Quill, CodeMirror, Monaco), a virtualised grid (AG Grid), a hover menu
(python.org), AJAX tables and paginated search (scrapethissite.com), cookie walls (OneTrust, Cookiebot), search as
you type (jsDelivr), Hebrew and Korean search, and a chart dashboard's table (Our World in Data)."""

import json
from dataclasses import replace
from typing import Any
from urllib.parse import unquote

from ..model import REAL_MAX_STEPS, Probe, Task, ci_tier, executed, last_status, one, path


def _extra(f: dict[str, Any]) -> Any:
    return f.get("extra")


def _blocked_unchanged(page_path: str, f: dict[str, Any], run: dict[str, Any]) -> bool:
    return last_status(run) == "blocked" and path(f) == page_path


def _wiki(article: str):
    def check(f: dict[str, Any], _: dict[str, Any]) -> bool:
        return unquote(path(f)) == article

    return check


RANGE_VALUE = "JSON.stringify((document.querySelector('input[type=range]') || {}).value ?? null)"
NOUI_FIRST = "JSON.stringify([...document.querySelectorAll('.noUi-handle')].slice(0, 2).map(h => h.getAttribute('aria-valuenow')))"
SORTABLE = "JSON.stringify([...document.querySelectorAll('#example1 > *')].map(e => e.innerText.trim()))"
SORTABLE_START = ["Item 1", "Item 2", "Item 3", "Item 4", "Item 5", "Item 6"]
# the texts of the page's editors: quilljs.com shows one of three (a carousel), the others are hidden slides
QUILL_TEXTS = "JSON.stringify([...document.querySelectorAll('.ql-editor')].map(e => e.innerText.trim()))"
CM_TEXT = "JSON.stringify((document.querySelector('.cm-content') || {}).innerText || null)"
MONACO_THEME = (
    "JSON.stringify({selected: [...document.querySelectorAll('select')].filter(s => [...s.options].some(o => "
    "o.text === 'High Contrast Dark')).map(s => s.selectedOptions[0] && s.selectedOptions[0].text), "
    "hc: !!document.querySelector('.monaco-editor.hc-black')})"
)
OSCARS = "JSON.stringify((document.querySelector('#table-body') || {}).innerText || '')"
COOKIES = "JSON.stringify(document.cookie)"
AG_SORT = (
    "JSON.stringify(([...document.querySelectorAll('.ag-header-cell')].find(c => c.innerText.trim() === 'Bank Balance')"
    " || {getAttribute: () => null}).getAttribute('aria-sort'))"
)


def _sortable_ok(f: dict[str, Any], run: dict[str, Any]) -> bool:
    items = _extra(f) or []
    if items == [*SORTABLE_START[1:], "Item 1"]:
        return True
    # drag and drop is not an act operation: a clean BLOCKED, the list as it was
    return _blocked_unchanged("/Sortable/", f, run) and items == SORTABLE_START


def _upload_blocked(f: dict[str, Any], run: dict[str, Any]) -> bool:
    # no upload operation: a clean BLOCKED on the page, nothing typed on the way
    return _blocked_unchanged("/upload", f, run) and "TYPE_TEXT" not in executed(run)


def _codemirror_ok(f: dict[str, Any], _: dict[str, Any]) -> bool:
    code = _extra(f) or ""
    return "console.log('notte')" in code and "'hello'" not in code and "new EditorView" in code


def _monaco_ok(f: dict[str, Any], _: dict[str, Any]) -> bool:
    theme = _extra(f) or {}
    return theme.get("selected") == ["High Contrast Dark"] or theme.get("hc") is True


def _cookie(f: dict[str, Any], name: str) -> str | None:
    for part in (_extra(f) or "").split("; "):
        key, _, value = part.partition("=")
        if key == name:
            return unquote(value)
    return None


def _onetrust_refused(f: dict[str, Any], _: dict[str, Any]) -> bool:
    # OptanonConsent is a query string: groups=C0001:1,C0002:0,...
    listed = one("?" + (_cookie(f, "OptanonConsent") or ""), "groups") or ""
    groups = dict(g.split(":", 1) for g in listed.split(",") if ":" in g)
    # the strictly necessary group: C0001, or 1 on sites that number their groups
    optional = {k: v for k, v in groups.items() if k not in ("C0001", "1")}
    return _cookie(f, "OptanonAlertBoxClosed") is not None and bool(optional) and set(optional.values()) == {"0"}


def _cookiebot_refused(f: dict[str, Any], _: dict[str, Any]) -> bool:
    consent = (_cookie(f, "CookieConsent") or "").replace(" ", "")
    return all(f"{k}:false" in consent for k in ("preferences", "statistics", "marketing"))


GOAL_HE = "חפשו בוויקיפדיה את הערך 'ירושלים' ופתחו אותו."
GOAL_KO = "위키백과에서 '경복궁'을 검색해서 문서를 열어 주세요."
SCRAPE = "https://www.scrapethissite.com/pages"
NOUI = "https://refreshless.com/nouislider/"
SORTABLE_URL = "https://sortablejs.github.io/Sortable/"
OWID = "https://ourworldindata.org/grapher/life-expectancy?tab=table"
AG_GRID = "https://www.ag-grid.com/example/"

TASKS = [
    # ---- sliders, drag and drop, file picker
    Task(
        "internet-slider",
        "https://the-internet.herokuapp.com/horizontal_slider",
        "Set the slider to 3.5.",
        lambda f, _: _extra(f) == "3.5",
        final_js=RANGE_VALUE,
        tags=("slider", "range"),
    ),
    Task(
        "nouislider",
        NOUI,
        "On the first slider of the page, set the lower handle to 40.",
        lambda f, _: (_extra(f) or [None])[0] in ("40", "40.0", "40.00"),
        final_js=NOUI_FIRST,
        tags=("slider", "aria-slider"),
    ),
    Task(
        "sortable-drag",
        SORTABLE_URL,
        "In the first list, move 'Item 1' to the end of the list.",
        _sortable_ok,
        final_js=SORTABLE,
        tags=("drag-and-drop", "capability"),
    ),
    Task(
        "uitap-upload",
        "http://uitestingplayground.com/upload",
        "Upload the file /tmp/notte-bench-upload.txt.",
        _upload_blocked,
        tags=("file-picker", "capability", "iframe"),
    ),
    # ---- rich editors
    Task(
        "quill-replace",
        "https://quilljs.com/",
        "Replace all the text in the editor with 'Hello from notte'.",
        lambda f, _: "Hello from notte" in json.loads(_extra(f) or "[]"),
        final_js=QUILL_TEXTS,
        tags=("rich-editor", "quill", "contenteditable"),
    ),
    Task(
        "codemirror-edit",
        "https://codemirror.net/try/",
        "In the script editor on the left, change console.log('hello') to console.log('notte'), keeping the rest of "
        "the script as it is.",
        _codemirror_ok,
        final_js=CM_TEXT,
        tags=("rich-editor", "codemirror", "contenteditable"),
    ),
    Task(
        "monaco-theme",
        "https://microsoft.github.io/monaco-editor/",
        "Switch the editor to the High Contrast Dark theme.",
        _monaco_ok,
        final_js=MONACO_THEME,
        tags=("rich-editor", "monaco", "select"),
    ),
    # ---- grids, menus, AJAX, pagination
    Task(
        "aggrid-sort",
        AG_GRID,
        "Sort the grid by Bank Balance, from the highest to the lowest.",
        lambda f, _: _extra(f) == "descending",
        final_js=AG_SORT,
        tags=("virtualised-grid", "sort"),
    ),
    Task(
        "python-menu",
        "https://www.python.org/",
        "Open the Quotes page from the About menu.",
        lambda f, _: path(f).rstrip("/") == "/about/quotes",
        tags=("hover-menu",),
    ),
    Task(
        "scrape-ajax",
        f"{SCRAPE}/ajax-javascript/",
        "Show the Oscar winning films of 2012.",
        lambda f, _: "Argo" in (_extra(f) or ""),
        final_js=OSCARS,
        tags=("ajax", "table"),
    ),
    Task(
        "scrape-hockey",
        f"{SCRAPE}/forms/",
        "Search the hockey teams for 'New', then go to the second page of the results.",
        lambda f, _: (
            path(f).rstrip("/") == "/pages/forms"
            and (one(f["url"], "q") or "").strip().lower() == "new"
            and one(f["url"], "page_num") == "2"
        ),
        tags=("search", "pagination"),
    ),
    Task(
        "jsdelivr-search",
        "https://www.jsdelivr.com/",
        "Find the npm package lodash and open its page.",
        lambda f, _: path(f).rstrip("/") == "/package/npm/lodash",
        tags=("search-as-you-type", "debounce"),
    ),
    # ---- cookie walls
    Task(
        "onetrust-refuse",
        "https://www.onetrust.com/",
        "Refuse all optional cookies.",
        _onetrust_refused,
        final_js=COOKIES,
        tags=("consent", "dark-pattern"),
    ),
    Task(
        "cookiebot-refuse",
        "https://www.cookiebot.com/en/",
        "Refuse all cookies except the strictly necessary ones.",
        _cookiebot_refused,
        final_js=COOKIES,
        tags=("consent",),
    ),
    # ---- RTL and CJK input on real sites
    Task(
        "he-wiki", "https://he.wikipedia.org/wiki/", GOAL_HE, _wiki("/wiki/ירושלים"), tags=("he", "rtl-input", "search")
    ),
    Task(
        "ko-wiki", "https://ko.wikipedia.org/wiki/", GOAL_KO, _wiki("/wiki/경복궁"), tags=("ko", "cjk-input", "search")
    ),
]
TASKS = [replace(t, max_steps=REAL_MAX_STEPS) for t in TASKS]

PROBES = [
    Probe(
        "nouislider-values",
        NOUI,
        "Which values is the first slider of the page set to?",
        ["20 and 80", "0 and 100", "40 and 60", "1450 and 2050"],
        "20 and 80",
    ),
    Probe(
        "sortable-first",
        SORTABLE_URL,
        "Which item is first in the first list?",
        ["Item 1", "Item 2", "Item 3", "Item 6"],
        "Item 1",
    ),
    Probe(
        "monaco-language",
        "https://microsoft.github.io/monaco-editor/",
        "In which programming language is the sample code in the editor?",
        ["TypeScript", "Python", "Java", "C#"],
        "TypeScript",
    ),
    Probe(
        "codemirror-logs",
        "https://codemirror.net/try/",
        "Which text does the example code log?",
        ["hello", "world", "notte", "nothing"],
        "hello",
    ),
    Probe(
        "quill-heading", "https://quilljs.com/", "Is the editor's first heading 'Quill Rich Text Editor'?", None, "YES"
    ),
    Probe(
        "python-quotes",
        "https://www.python.org/",
        "Does the About menu have a link to a Quotes page?",
        None,
        "YES",
    ),
    Probe(
        "scrape-andorra",
        f"{SCRAPE}/simple/",
        "What is the capital of Andorra?",
        ["Andorra la Vella", "Escaldes-Engordany", "Canillo", "Barcelona"],
        "Andorra la Vella",
    ),
    Probe(
        "scrape-afghanistan-area",
        f"{SCRAPE}/simple/",
        "What is the area of Afghanistan in km²?",
        ["647500.0", "468.0", "82880.0", "652230.0"],
        "647500.0",
    ),
    Probe(
        "scrape-bruins-wins",
        f"{SCRAPE}/forms/",
        "How many wins did the Boston Bruins have in 1990?",
        ["44", "31", "51", "36"],
        "44",
    ),
    Probe(
        "owid-top",
        OWID,
        "Which country or region has the highest life expectancy in this table?",
        ["Monaco", "Japan", "San Marino", "Hong Kong"],
        "Monaco",
    ),
    Probe("owid-san-marino", OWID, "Is San Marino's life expectancy above 85 years?", None, "YES"),
    Probe("onetrust-banner", "https://www.onetrust.com/", "Is a cookie consent banner shown?", None, "YES"),
    Probe("cookiebot-deny", "https://www.cookiebot.com/en/", "Is there a button to deny cookies?", None, "YES"),
    Probe(
        "ko-palace-city",
        "https://ko.wikipedia.org/wiki/경복궁",
        "In which city is this palace?",
        ["Seoul", "Busan", "Gyeongju", "Incheon"],
        "Seoul",
    ),
    Probe(
        "he-nyc-country",
        "https://he.wikipedia.org/wiki/ניו_יורק",
        "In which country is this city?",
        ["United States", "Canada", "Israel", "United Kingdom"],
        "United States",
    ),
]

# Core: the-internet, scrapethissite.com (a scraping sandbox) and Wikipedia. Extended: the other third-party sites
# (editors' and libraries' sites, AG Grid, python.org, jsDelivr, cookie platforms, Our World in Data), some with a known
# cause in the bench bug list: nouislider (17: no operation moves an ARIA slider), quill-replace (18: a contenteditable
# without a textbox role is not offered), uitap-upload (16: a click that opens a file chooser reports plain success)
TASKS = ci_tier(TASKS, core={"internet-slider", "scrape-ajax", "scrape-hockey", "he-wiki", "ko-wiki"})
PROBES = ci_tier(
    PROBES, core={"scrape-andorra", "scrape-afghanistan-area", "scrape-bruins-wins", "ko-palace-city", "he-nyc-country"}
)
