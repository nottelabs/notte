# pyright: basic
"""Local pages for what public sites cannot show reliably: a travel search (async combobox, date grid, guests
steppers), a sign-up wizard with validation errors, masked inputs, a contenteditable review, a cross-origin iframe,
nested shadow DOM, aria-labelledby and icon-only buttons, listbox and combobox, an off-canvas drawer with a range
input, a long page with lazy sections, and a German cookie wall. `fixtures/cov/`."""

import re
from dataclasses import replace
from typing import Any

from ..model import REAL_MAX_STEPS, Probe, Task, ci_tier, one, path


def _digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def _fixture(page: str, **expected: str):
    def check(f: dict[str, Any], _: dict[str, Any]) -> bool:
        return path(f).endswith("/cov/" + page) and all(one(f["url"], k) == v for k, v in expected.items())

    return check


def _masked_ok(f: dict[str, Any], _: dict[str, Any]) -> bool:
    u = f["url"]
    return (
        path(f).endswith("/cov/paid.html")
        and _digits(one(u, "phone")) == "5550109999"
        and _digits(one(u, "card")) == "4242424242424242"
        and _digits(one(u, "exp")) == "1228"
        and one(u, "cvc") == "123"
    )


def _review_ok(f: dict[str, Any], _: dict[str, Any]) -> bool:
    text = re.sub(r"\s+", " ", one(f["url"], "review") or "").strip().lower()
    return (
        path(f).endswith("/cov/posted.html")
        and one(f["url"], "rating") == "4"
        and text == "great lamp, easy to assemble."
    )


def _a11y_ok(f: dict[str, Any], _: dict[str, Any]) -> bool:
    u = f["url"]
    return (
        path(f).endswith("/cov/address-saved.html")
        and one(u, "ship_zip") == "75001"
        and one(u, "bill_zip") == "10115"
        # the other fields keep their values
        and one(u, "ship_street") == "12 Rue de la République"
        and one(u, "bill_street") == "3 Quai Saint-Antoine"
        and one(u, "ship_city") == "Lyon"
        and one(u, "bill_city") == "Lyon"
    )


TASKS = [
    Task(
        "f-trip",
        "{fixtures}/cov/trip.html",
        "Search for stays in Lisbon from 13 to 15 November 2026 for 2 adults and 1 child.",
        _fixture(
            "trip-results.html", dest="LIS", checkin="2026-11-13", checkout="2026-11-15", adults="2", children="1"
        ),
        tags=("travel", "combobox", "date-grid", "stepper", "icon-only", "popover"),
    ),
    Task(
        # f-trip without a form field named "children" (`form.children` then names the field, not the child elements)
        "f-trip-kids",
        "{fixtures}/cov/trip-kids.html",
        "Search for stays in Lisbon from 13 to 15 November 2026 for 2 adults and 1 child.",
        _fixture(
            "trip-kids-results.html", dest="LIS", checkin="2026-11-13", checkout="2026-11-15", adults="2", kids="1"
        ),
        tags=("travel", "combobox", "date-grid", "stepper", "icon-only", "popover"),
    ),
    Task(
        "f-wizard",
        "{fixtures}/cov/wizard.html",
        "Sign up with the email jane.doe@example.com and the password Sunflower42, as Jane Doe from Canada, and "
        "finish creating the account.",
        _fixture(
            "wizard-done.html",
            email="jane.doe@example.com",
            pw="Sunflower42",
            first="Jane",
            last="Doe",
            country="CA",
            terms="on",
        ),
        tags=("form", "wizard", "validation"),
    ),
    Task(
        "f-masked",
        "{fixtures}/cov/masked.html",
        "Pay with the card 4242 4242 4242 4242, expiry 12/28, CVC 123, and the phone number 555 010 9999.",
        _masked_ok,
        tags=("form", "masked-input", "disabled"),
    ),
    Task(
        "f-richtext",
        "{fixtures}/cov/richtext.html",
        "Post a 4-star review that says 'Great lamp, easy to assemble.'",
        _review_ok,
        tags=("form", "contenteditable", "hidden-radio"),
    ),
    Task(
        "f-xframe",
        "{fixtures}/cov/xframe.html",
        "Subscribe jane.doe@example.com to the Pro plan.",
        _fixture("xframe-done.html", email="jane.doe@example.com", plan="pro"),
        tags=("iframe", "cross-origin"),
    ),
    Task(
        "f-webcomp",
        "{fixtures}/cov/webcomp.html",
        "Place the order for Jane Doe, email jane.doe@example.com, with Express shipping.",
        _fixture("order-done.html", name="Jane Doe", email="jane.doe@example.com", speed="express"),
        tags=("shadow-dom", "web-components", "listbox"),
    ),
    Task(
        "f-a11y",
        "{fixtures}/cov/a11y.html",
        "Set the shipping postcode to 75001 and the billing postcode to 10115, then save.",
        _a11y_ok,
        tags=("a11y", "aria-labelledby", "icon-only", "hidden-label"),
    ),
    Task(
        "f-listbox",
        "{fixtures}/cov/listbox.html",
        "Choose the size Large, the colour Forest green and the pick-up store in Lyon, then continue.",
        _fixture("choice-done.html", size="L", color="forest", city="Lyon"),
        tags=("select", "listbox", "combobox"),
    ),
    Task(
        "f-drawer",
        "{fixtures}/cov/drawer.html",
        "Show only the Outdoor products that cost at most $50.",
        _fixture("drawer.html", cat="outdoor", max="50"),
        tags=("drawer", "range", "icon-only", "toast"),
    ),
    Task(
        "f-lazy",
        "{fixtures}/cov/lazy.html",
        "Open the full warranty terms of this lamp.",
        _fixture("warranty.html", product="lumi"),
        tags=("long-page", "lazy-load"),
    ),
    Task(
        "f-cookie-de",
        "{fixtures}/cov/cookie-de.html",
        "Open the contact page.",
        _fixture("kontakt.html"),
        tags=("de", "consent", "modal"),
    ),
]

PROBES = [
    Probe(
        "f-trip-adults",
        "{fixtures}/cov/trip.html",
        "For how many adults is the search set?",
        ["1", "2", "3", "4"],
        "1",
    ),
    Probe(
        "f-trip-kids-adults",
        "{fixtures}/cov/trip-kids.html",
        "For how many adults is the search set?",
        ["1", "2", "3", "4"],
        "1",
    ),
    Probe(
        "f-wizard-step",
        "{fixtures}/cov/wizard.html",
        "Which step of the sign-up is shown?",
        ["Step 1 of 3: Account", "Step 2 of 3: Profile", "Step 3 of 3: Review", "The sign-up is finished"],
        "Step 1 of 3: Account",
    ),
    Probe("f-pay-enabled", "{fixtures}/cov/masked.html", "Can the Pay button be clicked right now?", None, "NO"),
    Probe("f-review-empty", "{fixtures}/cov/richtext.html", "Is the review text still empty?", None, "YES"),
    Probe(
        "f-xframe-pro",
        "{fixtures}/cov/xframe.html",
        "How much does the Pro plan cost per year?",
        ["€42.00", "€12.00", "€99.00", "It is free"],
        "€42.00",
    ),
    Probe(
        "f-webcomp-speed",
        "{fixtures}/cov/webcomp.html",
        "Which shipping speed is selected?",
        ["Standard (5-7 days)", "Express (2 days)", "Overnight", "None"],
        "Standard (5-7 days)",
    ),
    Probe(
        "f-a11y-billing-zip",
        "{fixtures}/cov/a11y.html",
        "What is the billing postcode?",
        ["69001", "69002", "75001", "10115"],
        "69002",
    ),
    Probe(
        "f-a11y-delete",
        "{fixtures}/cov/a11y.html",
        "Is there a button to delete the shipping address?",
        None,
        "YES",
    ),
    Probe(
        "f-listbox-colour",
        "{fixtures}/cov/listbox.html",
        "Which colour is selected?",
        ["Ocean blue", "Forest green", "Sunset orange", "Slate grey"],
        "Ocean blue",
    ),
    Probe("f-drawer-open", "{fixtures}/cov/drawer.html", "Is the filters panel open?", None, "NO"),
    Probe(
        "f-lazy-reviews",
        "{fixtures}/cov/lazy.html",
        "Are any customer reviews shown on the page yet?",
        None,
        "NO",
    ),
    Probe("f-cookie-wall", "{fixtures}/cov/cookie-de.html", "Is a cookie consent dialog open?", None, "YES"),
]
# several widgets per task: more steps than the one-control fixtures
TASKS = [replace(t, max_steps=REAL_MAX_STEPS) for t in TASKS]

# local pages: core. f-trip and f-webcomp (bugs 1 and 2 in the bench bug list) and the f-trip-adults and f-drawer-open
# probes (bugs 1 and 9) fail until those fixes land: they stay in core as their regression tests. Extended:
# f-webcomp-speed, which Jev misses with the value in the element's label (a decider miss, not an observe bug).
TASKS = ci_tier(TASKS, core={t.name for t in TASKS})
PROBES = ci_tier(PROBES, core={p.name for p in PROBES} - {"f-webcomp-speed"})
