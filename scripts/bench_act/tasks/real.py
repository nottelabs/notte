# pyright: basic
"""Tasks and probes on real sites: Google Flights, booking.com, IKEA, GitHub, PyPI, Hacker News, jQuery UI demos,
Spiegel, ... These change and sometimes block or redirect a headless browser (see `rules.site_miss`)."""

import base64
from dataclasses import replace
from typing import Any

from ..model import REAL_MAX_STEPS, Probe, Task, ci_tier, executed, frame_value, one, path, visited

GF_HOME = "https://www.google.com/travel/flights?hl=en"
# one-way Paris -> Tokyo, 13 Nov 2026, as Google's own search page encodes it (captured from a manual search)
GF_RESULTS = (
    "https://www.google.com/travel/flights/search?"
    "tfs=CBwQAhooEgoyMDI2LTExLTEzagwIAxIIL20vMDVxdGpyDAgDEggvbS8wN2Rma0ABSAFwAYIBCwj___________8BmAEC&hl=en"
)
PARIS = {"/m/05qtj", "CDG", "ORY", "BVA", "PAR"}
TOKYO = {"/m/07dfk", "HND", "NRT", "TYO"}
# /m/059rby is New York State: Google's first suggestion for "New York" ("New York, USA")
NEW_YORK = {"/m/02_286", "/m/059rby", "JFK", "EWR", "LGA", "NYC"}


def _varint(buf: bytes, i: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        b = buf[i]
        i += 1
        value |= (b & 0x7F) << shift
        shift += 7
        if not b & 0x80:
            return value, i


def _protobuf(buf: bytes) -> list[tuple[int, Any]]:
    """Fields of a protobuf message, (field number, int or bytes); enough for Google Flights' `tfs`."""
    fields, i = [], 0
    while i < len(buf):
        key, i = _varint(buf, i)
        number, wire = key >> 3, key & 7
        if wire == 0:
            value, i = _varint(buf, i)
        elif wire == 2:
            n, i = _varint(buf, i)
            value, i = buf[i : i + n], i + n
        elif wire == 1:
            value, i = buf[i : i + 8], i + 8
        elif wire == 5:
            value, i = buf[i : i + 4], i + 4
        else:
            raise ValueError(f"wire type {wire}")
        fields.append((number, value))
    return fields


def gf_search(url: str) -> dict[str, Any] | None:
    """The legs of a Google Flights URL: date, origin / destination ids (city mids or airport codes), and the
    number of selected flight segments (a result was opened); `trip` is 2 for one-way, 1 for round trip."""
    tfs = one(url, "tfs")
    if not tfs:
        return None
    try:
        top = _protobuf(base64.urlsafe_b64decode(tfs + "=" * (-len(tfs) % 4)))
        legs = []
        for number, value in top:
            if number != 3:
                continue
            leg = _protobuf(value)

            def places(n: int, leg: list[tuple[int, Any]] = leg) -> set[str]:
                return {
                    v.decode() for f, m in leg if f == n for g, v in _protobuf(m) if g == 2 and isinstance(v, bytes)
                }

            legs.append(
                {
                    "date": next((v.decode() for f, v in leg if f == 2), None),
                    "from": places(13),
                    "to": places(14),
                    "segments": sum(1 for f, _ in leg if f == 4),
                }
            )
        trip = next((v for n, v in top if n == 19), None)
    except Exception:
        return None
    return {"legs": legs, "trip": trip}


def _gf_ok(page: str, legs: list[tuple[str, set[str], set[str]]], trip: int | None = None, opened: bool = False):
    def check(f: dict[str, Any], _: dict[str, Any]) -> bool:
        if path(f) != f"/travel/flights/{page}":
            return False
        search = gf_search(f["url"])
        if search is None or len(search["legs"]) != len(legs):
            return False
        if trip is not None and search["trip"] != trip:
            return False
        for leg, (date, origin, destination) in zip(search["legs"], legs, strict=True):
            if leg["date"] != date or not leg["from"] & origin or not leg["to"] & destination:
                return False
            if opened and leg["segments"] < 1:
                return False
        return True

    return check


def _booking_ok(f: dict[str, Any], _: dict[str, Any]) -> bool:
    u = f["url"]
    ss = (one(u, "ss") or "").lower()
    return (
        "/searchresults" in path(f)
        and one(u, "checkin") == "2026-11-13"
        and one(u, "checkout") == "2026-11-15"
        and one(u, "group_adults") == "2"
        and one(u, "no_rooms") in (None, "1")
        and ("lisbo" in ss or one(u, "dest_id") == "-2167973")
    )


def _ikea_ok(f: dict[str, Any], run: dict[str, Any]) -> bool:
    text = f.get("text") or ""
    in_cart = "Shopping Cart, 1 items" in text or "Shopping Cart, 1 item" in text
    sorted_once = any("sort=PRICE_LOW_TO_HIGH" in u for u in visited(run) + [f["url"]])
    return path(f) == "/be/en/shoppingcart/" and in_cart and "lamp" in text.lower() and sorted_once


def _saucedemo_ok(f: dict[str, Any], _: dict[str, Any]) -> bool:
    # the cheapest product is "Sauce Labs Onesie" ($7.99), item id 2
    return path(f) == "/cart.html" and (f.get("cart") or "").replace(" ", "") == "[2]"


def _github_ok(f: dict[str, Any], _: dict[str, Any]) -> bool:
    q = (one(f["url"], "q") or "").lower()
    return (
        path(f).rstrip("/") == "/pallets/flask/issues"
        and ("label:bug" in q or 'label:"bug"' in q)
        and "is:closed" not in q
        and "state:closed" not in q
    )


def _wiki_hops_ok(f: dict[str, Any], run: dict[str, Any]) -> bool:
    return path(f) == "/wiki/Colossus_computer" and "TYPE_TEXT" not in executed(run)


def _hn_ok(f: dict[str, Any], run: dict[str, Any]) -> bool:
    expected = (run.get("pre") or {}).get("top_id")
    return path(f) == "/item" and expected is not None and one(f["url"], "id") == expected


DEMOQA_EXPECTED = {
    "Student Name": "Jane Doe",
    "Student Email": "jane.doe@example.com",
    "Gender": "Female",
    "Mobile": "0123456789",
    "Date of Birth": "15 November,1990",
    "Subjects": "Maths",
    "Hobbies": "Reading",
    "State and City": "NCR Delhi",
}


def _demoqa_ok(f: dict[str, Any], _: dict[str, Any]) -> bool:
    rows = {r[0]: r[1] for r in f.get("tables") or [] if len(r) == 2}
    return all(rows.get(k) == v for k, v in DEMOQA_EXPECTED.items())


UPLOAD_NAME = "notte-bench-upload.txt"


def _upload_ok(f: dict[str, Any], _: dict[str, Any]) -> bool:
    return path(f) == "/upload" and "File Uploaded!" in (f.get("text") or "") and UPLOAD_NAME in (f.get("text") or "")


HN_PRE = "(() => { const a = document.querySelector('tr.athing'); return JSON.stringify({top_id: a && a.id}) })()"

_TASKS = [
    Task(
        "gf-oneway",
        GF_HOME,
        "Search for one-way flights from Paris to Tokyo on 13 November 2026.",
        _gf_ok("search", [("2026-11-13", PARIS, TOKYO)], trip=2),
        tags=("google-flights", "combobox", "date-picker", "consent"),
    ),
    Task(
        "gf-roundtrip",
        GF_HOME,
        "Search for round-trip flights from Paris to New York, leaving on 13 November 2026 and returning on "
        "20 November 2026.",
        _gf_ok("search", [("2026-11-13", PARIS, NEW_YORK), ("2026-11-20", NEW_YORK, PARIS)]),
        tags=("google-flights", "combobox", "date-picker", "consent"),
    ),
    Task(
        "gf-open",
        GF_RESULTS,
        "Open the first flight in the results list. Do not book or pay.",
        _gf_ok("booking", [("2026-11-13", PARIS, TOKYO)], opened=True),
        tags=("google-flights", "consent"),
    ),
    Task(
        "gf-book",
        GF_HOME,
        "Find one-way flights from Paris to Tokyo on 13 November 2026, then open the first flight in the results "
        "to select it. Do not book or pay.",
        _gf_ok("booking", [("2026-11-13", PARIS, TOKYO)], opened=True),
        tags=("google-flights", "end-to-end"),
    ),
    Task(
        "hotel",
        "https://www.booking.com/index.en-gb.html",
        "Search for hotels in Lisbon for 2 adults and 1 room, check-in on 13 November 2026 and check-out on "
        "15 November 2026.",
        _booking_ok,
        tags=("travel", "date-picker", "consent"),
    ),
    Task(
        "saucedemo",
        "https://www.saucedemo.com/",
        "Log in as standard_user with the password secret_sauce, sort the products by price from low to high, add "
        "the cheapest product to the cart, then open the cart.",
        _saucedemo_ok,
        tags=("e-commerce", "login", "select"),
    ),
    Task(
        "ikea",
        "https://www.ikea.com/be/en/",
        "Search IKEA for 'desk lamp', sort the results by price from low to high, open the first lamp in the "
        "results, add it to the shopping cart, then open the shopping cart.",
        _ikea_ok,
        tags=("e-commerce", "consent", "modal"),
    ),
    Task(
        "github",
        "https://github.com/",
        "Find the pallets/flask repository on GitHub, open its issues and show only the open issues with the "
        "label 'bug'.",
        _github_ok,
        tags=("dev", "search", "filter"),
    ),
    Task(
        "pypi",
        "https://pypi.org/",
        "Find the package 'requests' on PyPI and open the page of its release 2.31.0.",
        lambda f, _: path(f) == "/project/requests/2.31.0/",
        tags=("dev", "search"),
    ),
    Task(
        "wiki-hops",
        "https://en.wikipedia.org/wiki/Alan_Turing",
        "Without using the search box: from this article, follow the link to the Bletchley Park article, then "
        "from that article follow the link to the article about the Colossus computer.",
        _wiki_hops_ok,
        tags=("multi-hop", "below-fold"),
    ),
    Task(
        "hn",
        "https://news.ycombinator.com/",
        "Open the comments page of the top story.",
        _hn_ok,
        pre_js=HN_PRE,
        tags=("knowledge",),
    ),
    Task(
        "demoqa",
        "https://demoqa.com/automation-practice-form",
        "Fill in the student registration form: first name Jane, last name Doe, email jane.doe@example.com, "
        "gender Female, mobile 0123456789, date of birth 15 November 1990, subject Maths, hobby Reading, state "
        "NCR and city Delhi. Then submit the form.",
        _demoqa_ok,
        tags=("form", "date-picker", "combobox", "custom-select"),
    ),
    Task(
        "jq-datepicker",
        "https://jqueryui.com/datepicker/",
        "Pick 15 November 2026 in the date picker.",
        lambda f, _: frame_value(f, "datepicker") == "11/15/2026",
        tags=("iframe", "date-picker"),
    ),
    Task(
        "jq-selectmenu",
        "https://jqueryui.com/selectmenu/",
        "In the demo, set 'Select a speed' to Fast and 'Select a number' to 7.",
        lambda f, _: frame_value(f, "speed") == "Fast" and frame_value(f, "number") == "7",
        tags=("iframe", "custom-select"),
    ),
    Task(
        "consent",
        "https://www.spiegel.de/",
        "Open the Sport section.",
        lambda f, _: path(f).startswith("/sport/"),
        tags=("consent", "iframe"),
    ),
    Task(
        "newtab",
        "https://the-internet.herokuapp.com/windows",
        "Open the new window from the 'Click Here' link and switch to it.",
        lambda f, _: path(f) == "/windows/new",
        tags=("new-tab",),
    ),
    Task(
        "infinite",
        "https://www.scrapingcourse.com/infinite-scrolling",
        "Open the product 'Kenobi Trail Jacket'. More products load as you scroll down.",
        lambda f, _: path(f).rstrip("/").endswith("/product/kenobi-trail-jacket"),
        tags=("infinite-scroll",),
    ),
    Task(
        "loadmore",
        "https://www.scrapingcourse.com/button-click",
        "Open the product 'Montana Wind Jacket'.",
        lambda f, _: path(f).rstrip("/").endswith("/product/montana-wind-jacket"),
        tags=("load-more",),
    ),
    Task(
        "upload",
        "https://the-internet.herokuapp.com/upload",
        f"Upload the file /tmp/{UPLOAD_NAME}.",
        _upload_ok,
        tags=("file-upload", "capability"),
    ),
]
TASKS = [replace(t, max_steps=REAL_MAX_STEPS) for t in _TASKS]

BOOKING_RESULTS = (
    "https://www.booking.com/searchresults.en-gb.html?ss=Lisbon&checkin=2026-11-13&checkout=2026-11-15"
    "&group_adults=2&no_rooms=1&group_children=0"
)
FLASK_BUGS = "https://github.com/pallets/flask/issues?q=is%3Aissue%20state%3Aopen%20label%3Abug"
PROBES = [
    Probe(
        "gf-destination",
        GF_RESULTS,
        "Which city is the destination of this flight search?",
        ["Tokyo", "Paris", "Osaka", "Seoul"],
        "Tokyo",
    ),
    Probe("gf-oneway", GF_RESULTS, "Is this a one-way flight search?", None, "YES"),
    Probe(
        "gf-date",
        GF_RESULTS,
        "What is the departure date of this search?",
        ["Fri, Nov 13", "Sat, Nov 14", "Fri, Nov 20", "Thu, Nov 12"],
        "Fri, Nov 13",
    ),
    Probe(
        "hotel-city",
        BOOKING_RESULTS,
        "In which city are these hotels?",
        ["Lisbon", "Porto", "Madrid", "Barcelona"],
        "Lisbon",
    ),
    Probe("hotel-adults", BOOKING_RESULTS, "Is this search for 2 adults?", None, "YES"),
    Probe("gh-label", FLASK_BUGS, "Is the 'bug' label filter applied to this issue list?", None, "YES"),
    Probe(
        "gh-repo",
        FLASK_BUGS,
        "Which repository's issues are listed?",
        ["pallets/flask", "pallets/click", "django/django", "psf/requests"],
        "pallets/flask",
    ),
    Probe(
        "pypi-version",
        "https://pypi.org/project/requests/2.31.0/",
        "Which release of requests is this page about?",
        ["2.31.0", "2.32.3", "2.30.0", "2.28.2"],
        "2.31.0",
    ),
    Probe(
        "pypi-latest",
        "https://pypi.org/project/requests/2.31.0/",
        "Is this the latest version of requests?",
        None,
        "NO",
    ),
    Probe(
        "sauce-password",
        "https://www.saucedemo.com/",
        "Which password does the page give for all users?",
        ["secret_sauce", "standard_user", "SuperSecretPassword!", "admin"],
        "secret_sauce",
    ),
    Probe(
        "hn-more", "https://news.ycombinator.com/", "Is there a 'More' link to the next page of stories?", None, "YES"
    ),
    Probe(
        "turing-born",
        "https://en.wikipedia.org/wiki/Alan_Turing",
        "In which year was Alan Turing born?",
        ["1912", "1916", "1903", "1920"],
        "1912",
    ),
    Probe(
        "turing-bletchley",
        "https://en.wikipedia.org/wiki/Alan_Turing",
        "Does this article link to the Bletchley Park article?",
        None,
        "YES",
    ),
    Probe("jq-date-empty", "https://jqueryui.com/datepicker/", "Is the date picker's date field empty?", None, "YES"),
    Probe(
        "jq-speed",
        "https://jqueryui.com/selectmenu/",
        "Which speed is currently selected in the demo?",
        ["Slower", "Slow", "Medium", "Fast", "Faster"],
        "Medium",
    ),
    Probe(
        "spiegel-language",
        "https://www.spiegel.de/",
        "In which language is this news site?",
        ["German", "French", "English", "Dutch"],
        "German",
    ),
    Probe(
        "demoqa-female",
        "https://demoqa.com/automation-practice-form",
        "Is the Female gender option selected?",
        None,
        "NO",
    ),
    Probe(
        "demoqa-hobbies",
        "https://demoqa.com/automation-practice-form",
        "Which hobbies are checked?",
        ["None", "Sports", "Reading", "Music"],
        "None",
    ),
    Probe(
        "ikea-sorted",
        "https://www.ikea.com/be/en/search/?q=desk%20lamp",
        "Are these results sorted by price from low to high?",
        None,
        "NO",
    ),
    Probe(
        "infinite-kenobi",
        "https://www.scrapingcourse.com/infinite-scrolling",
        "Is the product 'Kenobi Trail Jacket' shown on the page right now?",
        None,
        "NO",
    ),
]

# third-party sites (Google, booking.com, IKEA, GitHub, PyPI, jQuery UI, Spiegel, demoqa, scrapingcourse): extended.
# Core: Wikipedia and the-internet only. `upload` is extended: act has no file upload, the task fails by design.
TASKS = ci_tier(TASKS, core={"wiki-hops", "newtab"})
PROBES = ci_tier(PROBES, core={"turing-born", "turing-bletchley", "hn-more"})
