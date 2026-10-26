# pyright: basic
"""Coverage of public sites the `demo` and `real` suites miss: e-commerce (filters, a quantity stepper, carts, a JS
alert), forms (radio groups, validation, a prefilled field, an overlapped field), tables (sort, search, pagination),
docs (search, a language select, tabs, an accordion), ARIA patterns (date picker dialog, combobox, radio group), React
selects, TodoMVC in Vue / Angular / Svelte, a JS confirm, and pages in Japanese, Arabic (RTL), German and French with
cookie walls. Each check reads the final page; `final_js` adds the state the page probe does not read."""

import json
import re
from dataclasses import replace
from typing import Any
from urllib.parse import unquote

from ..model import REAL_MAX_STEPS, Probe, Task, executed, one, path, visited


def _extra(f: dict[str, Any]) -> Any:
    return f.get("extra")


def _input(f: dict[str, Any], **match: str) -> dict[str, Any] | None:
    return next((i for i in f.get("inputs") or [] if all(i.get(k) == v for k, v in match.items())), None)


def _checked(f: dict[str, Any], input_id: str) -> bool:
    i = _input(f, id=input_id)
    return bool(i and i["checked"])


TABLE2_DUES = "JSON.stringify([...document.querySelectorAll('#table2 tbody tr .dues')].map(td => td.innerText.trim()))"


def _dues_desc_ok(f: dict[str, Any], _: dict[str, Any]) -> bool:
    dues = [float(d.strip("$")) for d in _extra(f) or []]
    return path(f) == "/tables" and len(dues) == 4 and dues == sorted(dues, reverse=True)


DT_ROWS = """JSON.stringify({info: (document.querySelector('.dt-info, .dataTables_info') || {}).innerText,
  rows: [...document.querySelectorAll('#example tbody tr')].map(tr => [...tr.cells].map(c => c.innerText.trim()))})"""


def _dt_tokyo_ok(f: dict[str, Any], _: dict[str, Any]) -> bool:
    extra = _extra(f) or {}
    rows = extra.get("rows") or []
    ages = [int(r[3]) for r in rows if len(r) > 3 and r[3].isdigit()]
    return (
        len(rows) >= 3
        and len(ages) == len(rows)
        and all(r[2] == "Tokyo" for r in rows)
        and ages == sorted(ages, reverse=True)
        and "filtered from 57" in (extra.get("info") or "")
    )


def _dt_page_ok(f: dict[str, Any], _: dict[str, Any]) -> bool:
    extra = _extra(f) or {}
    return (extra.get("info") or "").startswith("Showing 26 to 50 of 57") and len(extra.get("rows") or []) == 25


TOOLSHOP_CART = """JSON.stringify([...document.querySelectorAll('table tbody tr')].map(tr =>
  [(tr.querySelector('[data-test=product-title]') || tr.cells[0] || {}).innerText, (tr.querySelector('input') || {}).value]))"""


def _toolshop_cart_ok(f: dict[str, Any], _: dict[str, Any]) -> bool:
    rows = [(str(n or "").strip(), q) for n, q in _extra(f) or []]
    return path(f) == "/checkout" and rows == [("Claw Hammer", "3")]


DEMOBLAZE_CART = "JSON.stringify([...document.querySelectorAll('#tbodyid tr')].map(tr => tr.cells[1].innerText.trim()))"
SHOPCART_TEXT = "JSON.stringify(document.body.textContent)"


def _shopcart_ok(f: dict[str, Any], _: dict[str, Any]) -> bool:
    text = re.sub(r"\s+", " ", _extra(f) or "")
    cart = text[text.rfind("Cart") :]
    return (
        "Basic Cactus White T-shirt" in cart
        and "Quantity: 1" in cart
        and cart.count("Quantity:") == 1
        and re.search(r"SUBTOTAL\s*\$\s*13\.25", cart) is not None
    )


def _todos(f: dict[str, Any]) -> dict[str, bool]:
    return {t["text"].lower(): t["done"] for t in f.get("todos") or []}


def _todo_vue_ok(f: dict[str, Any], _: dict[str, Any]) -> bool:
    # the active filter shows only the two todos not completed
    return f["url"].endswith("#/active") and _todos(f) == {"buy milk": False, "pay rent": False}


def _datagouv_ok(f: dict[str, Any], run: dict[str, Any]) -> bool:
    # a dataset page, opened after a search about the air (any result: their titles vary, "polluants atmosphériques")
    searched = any("air" in unquote(one(u, "q") or "").lower() for u in visited(run) + [f["url"]])
    return re.fullmatch(r"/(fr/)?datasets/[^/]+/?", path(f)) is not None and searched


def _wiki(article: str):
    def check(f: dict[str, Any], _: dict[str, Any]) -> bool:
        return unquote(path(f)) == article

    return check


def _de_hop_ok(f: dict[str, Any], run: dict[str, Any]) -> bool:
    return unquote(path(f)) == "/wiki/Spree" and "TYPE_TEXT" not in executed(run)


def _value(js_selector: str) -> str:
    return f"JSON.stringify((document.querySelector({json.dumps(js_selector)}) || {{}}).value ?? null)"


def _attr(selectors: list[str], attribute: str) -> str:
    return (
        f"JSON.stringify({json.dumps(selectors)}.map(s => {{ const e = document.querySelector(s); "
        f"return e && e.getAttribute({json.dumps(attribute)}); }}))"
    )


REACT_SELECT_FIRST = (
    "JSON.stringify((document.querySelector('.basic-single [class*=single-value], .basic-single [class*=singleValue]') "
    "|| document.querySelector('[class*=singleValue]') || {}).innerText || null)"
)
MUI_MOVIE = (
    "JSON.stringify(([...document.querySelectorAll('input[role=combobox]')].find(e => e.labels && e.labels[0] && "
    "e.labels[0].innerText.trim() === 'Movie') || {}).value ?? null)"
)
BOOTSTRAP_FIRST = (
    "JSON.stringify([...document.querySelector('.accordion').querySelectorAll('.accordion-button')]"
    ".map(b => b.getAttribute('aria-expanded')))"
)

GOAL_JA = "ウィキペディアで「東京タワー」を検索して、その記事を開いてください。"
GOAL_AR = "ابحث في ويكيبيديا عن «برج إيفل» وافتح مقالته."
GOAL_DE = "Folge in diesem Artikel dem Link zum Artikel über die Spree, ohne die Suche zu benutzen."
GOAL_FR_DATA = "Cherchez des jeux de données sur la qualité de l'air, puis ouvrez l'un des jeux de données trouvés."
GOAL_FR_RECIPE = "Cherche une recette de crêpes et ouvre une des recettes trouvées."

TOOLSHOP = "https://practicesoftwaretesting.com"
CLAW_HAMMER = f"{TOOLSHOP}/product/01M5TR4FCSSP6VR0DGWM5AQ9FA"
APG = "https://www.w3.org/WAI/ARIA/apg/patterns"
UITAP = "http://uitestingplayground.com"
DATATABLES = "https://datatables.net/examples/basic_init/zero_configuration.html"


TASKS = [
    # ---- e-commerce
    Task(
        "toolshop-filter",
        TOOLSHOP + "/",
        "Show only the products in the Hammer category, sort them by price from low to high, then open the cheapest "
        "hammer.",
        lambda f, _: path(f) == "/product/01M5TR4FCZ1G3VM1PNC8PCKE6Q",  # Thor Hammer, $11.14
        tags=("e-commerce", "filter", "select", "angular"),
    ),
    Task(
        "toolshop-qty",
        CLAW_HAMMER,
        "Add 3 of this hammer to the cart, then open the cart.",
        _toolshop_cart_ok,
        final_js=TOOLSHOP_CART,
        tags=("e-commerce", "stepper", "cart", "angular"),
    ),
    Task(
        "demoblaze-cart",
        "https://www.demoblaze.com/",
        "Add the laptop 'Sony vaio i5' to the cart, then open the cart.",
        lambda f, _: path(f) == "/cart.html" and _extra(f) == ["Sony vaio i5"],
        final_js=DEMOBLAZE_CART,
        tags=("e-commerce", "js-alert", "cart"),
    ),
    Task(
        "shopcart-size",
        "https://react-shopping-cart-67954.firebaseapp.com/",
        "Show only the products available in size ML, then add the cheapest of them to the cart.",
        _shopcart_ok,
        final_js=SHOPCART_TEXT,
        tags=("e-commerce", "filter", "react", "drawer"),
    ),
    # ---- forms
    Task(
        "expand-radio",
        "https://practice.expandtesting.com/radio-buttons",
        "Choose Yellow as the favourite color and Football as the favourite sport.",
        lambda f, _: _checked(f, "yellow") and _checked(f, "football") and not _checked(f, "blue"),
        tags=("form", "radio"),
    ),
    Task(
        "expand-validation",
        "https://practice.expandtesting.com/form-validation",
        "Register with the contact name Jane Doe, the contact number 012-3456789, the pick-up date 15 November 2026 "
        "and payment by card.",
        lambda f, _: path(f) == "/form-confirmation",
        tags=("form", "validation", "date", "select", "prefilled"),
    ),
    Task(
        "uitap-sampleapp",
        UITAP + "/sampleapp",
        "Log in with the user name notte and the password pwd.",
        lambda f, _: "Welcome, notte!" in (f.get("text") or ""),
        tags=("form", "login", "dynamic-id"),
    ),
    Task(
        "uitap-overlapped",
        UITAP + "/overlapped",
        "Type Jane Doe in the Name field.",
        lambda f, _: _extra(f) == "Jane Doe",
        final_js=_value("#name"),
        tags=("form", "overlapped", "scroll-container"),
    ),
    Task(
        "uitap-textinput",
        UITAP + "/textinput",
        "Rename the button to 'Notte Button' with the text field, then click it.",
        lambda f, _: (_extra(f) or "").strip() == "Notte Button",
        final_js="JSON.stringify(document.querySelector('#updatingButton').innerText)",
        tags=("form",),
    ),
    # ---- tables
    Task(
        "tables-sort",
        "https://the-internet.herokuapp.com/tables",
        "Sort the second table (Example 2) by Due, from the highest amount to the lowest.",
        _dues_desc_ok,
        final_js=TABLE2_DUES,
        tags=("table", "sort"),
    ),
    Task(
        "dt-filter",
        DATATABLES,
        "Show only the employees whose office is in Tokyo, sorted by age from the oldest to the youngest.",
        _dt_tokyo_ok,
        final_js=DT_ROWS,
        tags=("table", "search", "sort"),
    ),
    Task(
        "dt-page",
        DATATABLES,
        "Show 25 entries per page, then go to the second page of the table.",
        _dt_page_ok,
        final_js=DT_ROWS,
        tags=("table", "pagination", "select"),
    ),
    # ---- dialogs
    Task(
        "js-confirm",
        "https://the-internet.herokuapp.com/javascript_alerts",
        "Open the JS confirm dialog and confirm it with OK.",
        lambda f, _: "You clicked: Ok" in (f.get("text") or ""),
        tags=("dialog", "js-confirm"),
    ),
    # ---- docs
    Task(
        "mdn-search",
        "https://developer.mozilla.org/en-US/",
        "Use the site search to find the reference page of the JavaScript array method flatMap(), and open it.",
        lambda f, _: path(f).rstrip("/").endswith("/Web/JavaScript/Reference/Global_Objects/Array/flatMap"),
        tags=("docs", "search", "combobox"),
    ),
    Task(
        "pydocs-lang",
        "https://docs.python.org/3/",
        "Switch this documentation to French.",
        lambda f, _: f["url"].startswith("https://docs.python.org/fr/"),
        tags=("docs", "select", "navigation"),
    ),
    Task(
        "vue-search",
        "https://vuejs.org/guide/introduction.html",
        "Search the Vue docs for 'watchers' and open the Watchers guide page.",
        lambda f, _: path(f).removesuffix(".html") == "/guide/essentials/watchers",
        tags=("docs", "search", "modal", "spa"),
    ),
    Task(
        "bootstrap-accordion",
        "https://getbootstrap.com/docs/5.3/components/accordion/",
        "In the first accordion example, expand 'Accordion Item #3'.",
        lambda f, _: (_extra(f) or [None] * 3)[2] == "true",
        final_js=BOOTSTRAP_FIRST,
        tags=("docs", "accordion"),
    ),
    Task(
        "apg-tabs",
        APG + "/tabs/examples/tabs-manual/",
        "Show the tab about Peter Müller.",
        lambda f, _: _extra(f) == ["true"],
        final_js=_attr(["#tab-4"], "aria-selected"),
        tags=("a11y", "tabs"),
    ),
    # ---- dropdowns, pickers, radio groups (ARIA patterns)
    Task(
        "apg-datepicker",
        APG + "/dialog-modal/examples/datepicker-dialog/",
        "Choose the date 15 November 2026 with the date picker.",
        lambda f, _: _extra(f) == "11/15/2026",
        final_js=_value("#id-textbox-1"),
        tags=("date-picker", "dialog", "grid"),
    ),
    Task(
        "apg-combobox",
        APG + "/combobox/examples/combobox-autocomplete-list/",
        "Choose the state Oregon in the States combobox.",
        lambda f, _: _extra(f) == "Oregon",
        final_js=_value("#cb1-input"),
        tags=("combobox", "autocomplete"),
    ),
    Task(
        "apg-radio",
        APG + "/radio/examples/radio-activedescendant/",
        "Order a thin crust pizza for home delivery.",
        lambda f, _: _extra(f) == ["true", "true"],
        final_js=_attr(["#rb13", "#rb22"], "aria-checked"),
        tags=("radio", "aria"),
    ),
    Task(
        "react-select",
        "https://react-select.com/home",
        "In the first select of the page, choose Purple.",
        lambda f, _: _extra(f) == "Purple",
        final_js=REACT_SELECT_FIRST,
        tags=("combobox", "react", "custom-select"),
    ),
    Task(
        "mui-autocomplete",
        "https://mui.com/material-ui/react-autocomplete/",
        "In the Combo box demo, choose the movie Pulp Fiction.",
        lambda f, _: _extra(f) == "Pulp Fiction",
        final_js=MUI_MOVIE,
        tags=("combobox", "react", "autocomplete"),
    ),
    # ---- SPAs
    Task(
        "todo-vue",
        "https://todomvc.com/examples/vue/dist/",
        "Add the todos 'buy milk', 'walk the dog' and 'pay rent', mark 'walk the dog' as completed, then show only "
        "the active todos.",
        _todo_vue_ok,
        tags=("spa", "vue", "routing"),
    ),
    Task(
        "todo-angular",
        "https://todomvc.com/examples/angular/dist/browser/",
        "Add the todos 'buy milk' and 'walk the dog', mark 'buy milk' as completed, then clear the completed todos.",
        lambda f, _: _todos(f) == {"walk the dog": False},
        tags=("spa", "angular"),
    ),
    Task(
        "todo-svelte",
        "https://todomvc.com/examples/svelte/dist/",
        "Add the todos 'call mom', 'book flights' and 'pay rent', then mark all of them as completed.",
        lambda f, _: _todos(f) == {"call mom": True, "book flights": True, "pay rent": True},
        tags=("spa", "svelte", "hidden-input"),
    ),
    # ---- non-English pages and cookie walls
    Task("ja-wiki", "https://ja.wikipedia.org/wiki/", GOAL_JA, _wiki("/wiki/東京タワー"), tags=("ja", "search")),
    Task("ar-wiki", "https://ar.wikipedia.org/wiki/", GOAL_AR, _wiki("/wiki/برج_إيفل"), tags=("ar", "rtl", "search")),
    Task("de-wiki-hop", "https://de.wikipedia.org/wiki/Berlin", GOAL_DE, _de_hop_ok, tags=("de", "long-page")),
    Task(
        "datagouv",
        "https://www.data.gouv.fr/datasets",
        GOAL_FR_DATA,
        _datagouv_ok,
        tags=("fr", "search", "open-data", "spa"),
    ),
    Task(
        "lemonde",
        "https://www.lemonde.fr/",
        "Open the International section.",
        lambda f, _: path(f).startswith("/international/"),
        tags=("fr", "consent", "news"),
    ),
    Task(
        "marmiton",
        "https://www.marmiton.org/",
        GOAL_FR_RECIPE,
        lambda f, _: path(f).startswith("/recettes/recette_") and "crepe" in path(f),
        tags=("fr", "consent", "search"),
    ),
]

PROBES = [
    # ---- the-internet pages not used yet
    Probe(
        "tables-email",
        "https://the-internet.herokuapp.com/tables",
        "What is Frank Bach's email address?",
        ["fbach@yahoo.com", "jdoe@hotmail.com", "jsmith@gmail.com", "tconway@earthlink.net"],
        "fbach@yahoo.com",
    ),
    Probe("tables-due", "https://the-internet.herokuapp.com/tables", "Does Jason Doe owe $100.00?", None, "YES"),
    Probe(
        "frames-middle",
        "https://the-internet.herokuapp.com/nested_frames",
        "Which word does the middle frame of the top row show?",
        ["LEFT", "MIDDLE", "RIGHT", "BOTTOM"],
        "MIDDLE",
    ),
    Probe(
        "frames-bottom",
        "https://the-internet.herokuapp.com/nested_frames",
        "Is there a frame showing BOTTOM?",
        None,
        "YES",
    ),
    Probe(
        "slider-value",
        "https://the-internet.herokuapp.com/horizontal_slider",
        "What is the slider's current value?",
        ["0", "2.5", "5", "4"],
        "0",
    ),
    # ---- tables
    Probe("dt-total", DATATABLES, "How many entries does the table have in total?", ["10", "25", "57", "100"], "57"),
    Probe(
        "dt-first",
        DATATABLES,
        "Who is in the first row of the table?",
        ["Airi Satou", "Tiger Nixon", "Zorita Serrano", "Angelica Ramos"],
        "Airi Satou",
    ),
    Probe("dt-first-page", DATATABLES, "Is the table showing its first page of entries?", None, "YES"),
    # ---- ARIA patterns
    Probe(
        "apg-tab-selected",
        APG + "/tabs/examples/tabs-manual/",
        "Which tab is selected?",
        ["Maria Ahlefeldt", "Carl Andersen", "Ida da Fonseca", "Peter Müller"],
        "Maria Ahlefeldt",
    ),
    Probe("apg-switch", APG + "/switch/examples/switch/", "Are notifications turned on?", None, "NO"),
    Probe(
        "apg-condiments",
        APG + "/checkbox/examples/checkbox-mixed/",
        "Which condiments are checked?",
        ["Only Tomato", "Lettuce and Tomato", "All of them", "None of them"],
        "Only Tomato",
    ),
    Probe("apg-all-condiments", APG + "/checkbox/examples/checkbox-mixed/", "Are all condiments checked?", None, "NO"),
    Probe("apg-crust", APG + "/radio/examples/radio-activedescendant/", "Is a pizza crust already chosen?", None, "NO"),
    Probe("apg-date-empty", APG + "/dialog-modal/examples/datepicker-dialog/", "Is the date field empty?", None, "YES"),
    Probe(
        "apg-rating",
        APG + "/slider/examples/slider-rating/",
        "Has a rating been chosen on the slider?",
        None,
        "NO",
    ),
    # ---- uitestingplayground
    Probe(
        "uitap-fruits",
        UITAP + "/select",
        "Which fruits are selected in the fruits list?",
        ["Apple, Cherry and Grape", "Only Apple", "Banana and Date", "None"],
        "Apple, Cherry and Grape",
    ),
    Probe("uitap-language", UITAP + "/select", "Has a programming language been selected?", None, "NO"),
    Probe("uitap-guid-empty", UITAP + "/shadowdom", "Is the GUID field empty?", None, "YES"),
    # ---- e-commerce
    Probe(
        "toolshop-price",
        CLAW_HAMMER,
        "What is the price of this product?",
        ["$11.48", "$13.41", "$12.58", "$11.14"],
        "$11.48",
    ),
    Probe(
        "toolshop-brand",
        CLAW_HAMMER,
        "Which brand makes this product?",
        ["MightyCraft Hardware", "ForgeFlex Tools", "Bosch", "Stanley"],
        "MightyCraft Hardware",
    ),
    Probe("toolshop-qty1", CLAW_HAMMER, "Is the quantity set to 1?", None, "YES"),
    Probe(
        "demoblaze-price",
        "https://www.demoblaze.com/prod.html?idp_=8",
        "What is the price of this laptop?",
        ["$790", "$650", "$1100", "$360"],
        "$790",
    ),
    Probe(
        "shopcart-count",
        "https://react-shopping-cart-67954.firebaseapp.com/",
        "How many products are found?",
        ["10", "16", "2", "20"],
        "16",
    ),
    # ---- forms
    Probe(
        "expand-color",
        "https://practice.expandtesting.com/radio-buttons",
        "Which favourite color is selected?",
        ["Blue", "Red", "Yellow", "Green"],
        "Blue",
    ),
    Probe(
        "expand-green",
        "https://practice.expandtesting.com/radio-buttons",
        "Can Green be chosen as the favourite color?",
        None,
        "NO",
    ),
    Probe(
        "expand-checkboxes",
        "https://practice.expandtesting.com/checkboxes",
        "Which checkboxes are checked?",
        ["Only Checkbox 1", "Only Checkbox 2", "Both", "Neither"],
        "Only Checkbox 2",
    ),
    Probe(
        "expand-name-empty",
        "https://practice.expandtesting.com/form-validation",
        "Is the contact name field empty?",
        None,
        "NO",
    ),
    # ---- docs
    Probe(
        "pydocs-version",
        "https://docs.python.org/3.12/",
        "Which Python version is this documentation for?",
        ["3.12", "3.13", "3.11", "3.14"],
        "3.12",
    ),
    Probe("pydocs-english", "https://docs.python.org/3.12/", "Is this documentation in English?", None, "YES"),
    Probe(
        "mdn-flatmap",
        "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Array/flatMap",
        "flatMap() is equivalent to which method followed by flat() of depth 1?",
        ["map()", "filter()", "reduce()", "forEach()"],
        "map()",
    ),
    Probe(
        "bs-expanded",
        "https://getbootstrap.com/docs/5.3/components/accordion/",
        "In the first accordion example, which item is expanded?",
        ["Accordion Item #1", "Accordion Item #2", "Accordion Item #3", "None"],
        "Accordion Item #1",
    ),
    Probe(
        "rs-first",
        "https://react-select.com/home",
        "Which colour is selected in the first select of the page?",
        ["Ocean", "Blue", "Purple", "Red"],
        "Ocean",
    ),
    Probe(
        "rs-multi",
        "https://react-select.com/home",
        "Are Purple and Red selected in the multi-select example?",
        None,
        "YES",
    ),
    # ---- non-English pages
    Probe(
        "ja-tower-year",
        "https://ja.wikipedia.org/wiki/東京タワー",
        "In which year was Tokyo Tower completed?",
        ["1958", "1964", "1970", "2012"],
        "1958",
    ),
    Probe(
        "ar-eiffel-city",
        "https://ar.wikipedia.org/wiki/برج_إيفل",
        "In which city is the tower of this article?",
        ["Paris", "London", "Cairo", "Dubai"],
        "Paris",
    ),
    Probe("ar-arabic", "https://ar.wikipedia.org/wiki/برج_إيفل", "Is this article written in Arabic?", None, "YES"),
    Probe(
        "de-berlin-river",
        "https://de.wikipedia.org/wiki/Berlin",
        "Which river flows through the city of this article?",
        ["Spree", "Elbe", "Rhein", "Donau"],
        "Spree",
    ),
    Probe(
        "fr-hugo-born",
        "https://fr.wikipedia.org/wiki/Victor_Hugo",
        "In which year was the subject of this article born?",
        ["1802", "1815", "1789", "1830"],
        "1802",
    ),
]
TASKS = [replace(t, max_steps=REAL_MAX_STEPS) for t in TASKS]
