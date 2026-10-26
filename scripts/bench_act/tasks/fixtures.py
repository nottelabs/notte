# pyright: basic
"""Tasks and probes on the local pages in `fixtures/`: one control or page structure each (autocomplete, long
select, radios and dates, below the fold, iframe, shadow DOM, cookie modal). No site noise: they must always pass."""

from typing import Any

from ..model import Probe, Task, ci_tier, one, path, qs, query_ok


def _form_ok(f: dict[str, Any], _: dict[str, Any]) -> bool:
    u = f["url"]
    return (
        path(f).endswith("/thanks.html")
        and one(u, "fullname") == "Jane Doe"
        and one(u, "email") == "jane.doe@example.com"
        and one(u, "plan") == "pro"
        and one(u, "terms") == "accepted"
        and "newsletter" not in qs(u)
    )


def _shadow_ok(f: dict[str, Any], _: dict[str, Any]) -> bool:
    message = (one(f["url"], "message") or "").strip().rstrip(".!").lower()
    return path(f).endswith("/sent.html") and one(f["url"], "name") == "Jane Doe" and message == "hello"


TASKS = [
    Task(
        "search",
        "{fixtures}/search.html",
        "Search the docs for billing and open the Billing FAQ article.",
        query_ok("/item.html", id="billing-faq"),
    ),
    Task(
        "form",
        "{fixtures}/form.html",
        "Create an account for Jane Doe, email jane.doe@example.com, on the Pro plan. "
        "Accept the terms and do not subscribe to the newsletter.",
        _form_ok,
    ),
    Task(
        "autocomplete",
        "{fixtures}/autocomplete.html",
        "Search flights to Lisbon.",
        query_ok("/flights.html", code="LIS"),
    ),
    Task(
        "coupon",
        "{fixtures}/coupon.html",
        "Apply the coupon code SAVE20.",
        query_ok("/applied.html", code="SAVE20"),
    ),
    Task(
        "country",
        "{fixtures}/country.html",
        "Set the country to Portugal and save the address.",
        query_ok("/saved.html", country="PT"),
        tags=("long-select",),
    ),
    Task(
        "booking",
        "{fixtures}/booking.html",
        "Book 3 VIP tickets for 15 November 2026.",
        query_ok("/booked.html", type="vip", qty="3", date="2026-11-15"),
        tags=("radio", "number", "date"),
    ),
    Task(
        "scroll",
        "{fixtures}/report.html",
        "Download the Q3 report.",
        query_ok("/download.html", report="q3"),
        tags=("below-fold",),
    ),
    Task(
        "iframe",
        "{fixtures}/newsletter.html",
        "Subscribe jane.doe@example.com to the newsletter.",
        query_ok("/subscribed.html", email="jane.doe@example.com"),
        tags=("iframe",),
    ),
    Task(
        "shadow",
        "{fixtures}/contact.html",
        "Send the message 'Hello' with the name Jane Doe.",
        _shadow_ok,
        tags=("shadow-dom",),
    ),
    Task(
        "cookie",
        "{fixtures}/landing.html",
        "Open the Pricing page.",
        lambda f, _: path(f).endswith("/pricing.html"),
        tags=("modal",),
    ),
]

PROBES = [
    Probe(
        "plan-selected",
        "{fixtures}/form.html",
        "Which plan is currently selected?",
        ["Free", "Pro", "Team", "No plan selected yet"],
        "No plan selected yet",
    ),
    Probe(
        "order-total",
        "{fixtures}/coupon.html",
        "What is the order total?",
        ["$96.00", "$120.00", "$100.00", "$20.00"],
        "$120.00",
    ),
    Probe(
        "newsletter-checked", "{fixtures}/form.html", "Is the newsletter subscription checkbox checked?", None, "YES"
    ),
    Probe("terms-accepted", "{fixtures}/form.html", "Are the terms of service accepted?", None, "NO"),
    Probe("coupon-applied", "{fixtures}/coupon.html", "Has a coupon been applied to this order?", None, "NO"),
]

# local pages: all in the CI core tier
TASKS = ci_tier(TASKS, core={t.name for t in TASKS})
PROBES = ci_tier(PROBES, core={p.name for p in PROBES})
