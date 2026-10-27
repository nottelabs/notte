# pyright: basic
"""Local pages, round 3 (`fixtures/cov3/`): a checkout wizard with validation errors and a back step, masked date and
phone fields with a ticket stepper, a client-side routed help center, a store finder in nested cross-origin frames, an
infinite scroll on the page itself, a paged table with icon-only buttons, a Spanish cookie dialog in a cross-origin
frame, an inbox named by titles and aria-labelledby chains, a submit button disabled until the form is valid (with an
async name check), and an Undo toast that disappears."""

import json
from dataclasses import replace
from typing import TypedDict, cast

from ..model import REAL_MAX_STEPS, JsonValue, Probe, Task, ci_tier, one, path


def _page(page: str, **expected: str):
    def check(f: dict[str, JsonValue], _: dict[str, JsonValue]) -> bool:
        return path(f).endswith("/cov3/" + page) and all(one(cast(str, f["url"]), k) == v for k, v in expected.items())

    return check


def _clicked(run: dict[str, JsonValue], label: str) -> bool:
    return any(
        s.get("operation") == "CLICK" and (s.get("target_label") or "").strip() == label
        for s in cast(list[dict[str, str | None]], run.get("steps", []))
        if s.get("status") == "executed"
    )


def _wizard_ok(f: dict[str, JsonValue], run: dict[str, JsonValue]) -> bool:
    # the goal asks to switch to express from the review step: Back must have been used
    ordered = _page(
        "wizard-done.html",
        name="Ana Ruiz",
        email="ana.ruiz@example.com",
        zip="28013",
        date="05/12/2026",
        speed="express",
        back_from="3",
    )
    return ordered(f, run) and _clicked(run, "Back")


# the help article on screen, and whether its first question's answer is open and visible
SPA_VIEW = """JSON.stringify({h1: (document.querySelector('#view h1') || {}).innerText || null,
  questions: [...document.querySelectorAll('#view .q')].map(q => { const b = q.querySelector('button'),
    a = q.querySelector('[role=region]'); return {q: b.innerText, open: b.getAttribute('aria-expanded') === 'true',
    shown: !a.hidden && a.getBoundingClientRect().height > 0}; })})"""


class _Question(TypedDict):
    q: str
    open: bool
    shown: bool


class _SpaView(TypedDict, total=False):
    h1: str | None
    questions: list[_Question]


def _spa_ok(f: dict[str, JsonValue], _: dict[str, JsonValue]) -> bool:
    view = cast(_SpaView, f.get("extra") or {})
    stored = next((q for q in view.get("questions") or [] if q["q"] == "Is my card stored?"), None)
    return (
        path(f).endswith("/cov3/spa.html")
        and one(cast(str, f["url"]), "topic") == "billing"
        and one(cast(str, f["url"]), "article") == "card"
        and view.get("h1") == "Change my payment card"
        and stored is not None
        and stored.get("open") is True
        and stored.get("shown") is True
    )


def _cookie_refused(f: dict[str, JsonValue], _: dict[str, JsonValue]) -> bool:
    try:
        consent = json.loads(cast(str, f.get("consent") or "null"))
    except ValueError:
        return False
    return path(f).endswith("/cov3/contacto.html") and consent == {"analytics": False, "ads": False, "social": False}


INBOX = """JSON.stringify([...document.querySelectorAll('#inbox li, #archived li')].map(li => ({id: li.dataset.id,
  list: li.parentElement.id, starred: (li.querySelector('[data-star]') || {getAttribute: () => null}).getAttribute('aria-pressed')})))"""


def _inbox_ok(f: dict[str, JsonValue], _: dict[str, JsonValue]) -> bool:
    rows = {r["id"]: r for r in cast(list[dict[str, str | None]], f.get("extra") or [])}
    return rows == {
        "m1": {"id": "m1", "list": "archived", "starred": None},
        "m2": {"id": "m2", "list": "inbox", "starred": "true"},
        "m3": {"id": "m3", "list": "inbox", "starred": "false"},
        "m4": {"id": "m4", "list": "inbox", "starred": "false"},
    }


FILES = """JSON.stringify({files: [...document.querySelectorAll('#files li span')].map(s => s.innerText),
  log: (document.body.dataset.log || '').split(' ').filter(Boolean)})"""


def _toast_ok(f: dict[str, JsonValue], _: dict[str, JsonValue]) -> bool:
    state = cast(dict[str, list[str]], f.get("extra") or {})
    log = state.get("log") or []
    # report.pdf back in the list, restored with Undo, and no other file deleted on the way
    return (
        "report.pdf" in (state.get("files") or [])
        and "restored:report.pdf" in log
        and [e for e in log if e.startswith("deleted:")] == ["deleted:report.pdf"]
    )


def _validsubmit_ok(f: dict[str, JsonValue], run: dict[str, JsonValue]) -> bool:
    try:
        checked = json.loads(one(cast(str, f.get("url") or ""), "checked") or "[]")
    except ValueError:
        return False
    return (
        isinstance(checked, list)
        and "acme" in checked
        and "acme studio" in checked
        and checked.index("acme") < checked.index("acme studio")
        and _page("workspace-done.html", ws="Acme Studio", pw="Blue-Kite-2026")(f, run)
    )


TASKS = [
    Task(
        "f3-wizard",
        "{fixtures}/cov3/wizard.html",
        "Order for Ana Ruiz (ana.ruiz@example.com), delivered to postcode 28013 on 5 December 2026 with standard "
        "delivery. On the review step, go back and switch to express delivery, then place the order.",
        _wizard_ok,
        tags=("wizard", "validation", "back-step", "masked-date"),
    ),
    Task(
        "f3-masked",
        "{fixtures}/cov3/masked.html",
        "Buy 4 tickets for María López, born on 3 July 1991, mobile phone +34 612 345 678.",
        _page("masked-done.html", name="María López", birth="03/07/1991", cc="+34", phone="612 345 678", qty="4"),
        tags=("masked-input", "stepper", "title-only", "disabled-until-valid"),
    ),
    Task(
        "f3-spa",
        "{fixtures}/cov3/spa.html",
        "In the help center, open the Billing topic, then the article about changing the payment card, and show the "
        "answer to 'Is my card stored?'.",
        _spa_ok,
        final_js=SPA_VIEW,
        tags=("spa", "client-routing", "accordion"),
    ),
    Task(
        "f3-xframe",
        "{fixtures}/cov3/xframe.html",
        "Pick up the order at the Chamberí store, with the pick-up notice sent to jane.doe@example.com.",
        _page("xframe-done.html", store="chamberi", email="jane.doe@example.com"),
        tags=("iframe", "cross-origin", "nested-iframe", "title-only"),
    ),
    Task(
        "f3-scroll",
        "{fixtures}/cov3/scroll.html",
        "Open Product 57.",
        _page("product.html", id="57"),
        tags=("infinite-scroll", "lazy-load"),
    ),
    Task(
        "f3-table",
        "{fixtures}/cov3/table.html",
        "Download invoice INV-1037.",
        _page("download.html", id="INV-1037"),
        tags=("table", "pagination", "icon-only", "title-only"),
    ),
    Task(
        "f3-cookie",
        "{fixtures}/cov3/cookie.html",
        "Rechaza todas las cookies opcionales y abre la página de contacto.",
        _cookie_refused,
        tags=("es", "consent", "dark-pattern", "iframe", "cross-origin"),
    ),
    Task(
        "f3-inbox",
        "{fixtures}/cov3/inbox.html",
        "Archive Paula's message about the invoice, and star Sam's message.",
        _inbox_ok,
        final_js=INBOX,
        tags=("a11y", "aria-labelledby", "title-only", "icon-only", "hidden-label"),
    ),
    Task(
        "f3-validsubmit",
        "{fixtures}/cov3/validsubmit.html",
        "Create a workspace named Acme with the password Blue-Kite-2026. If the name Acme is taken, name it Acme Studio "
        "instead.",
        _validsubmit_ok,
        tags=("disabled-until-valid", "async-validation"),
    ),
    Task(
        "f3-toast",
        "{fixtures}/cov3/toast.html",
        "The file report.pdf was just deleted by mistake: restore it.",
        _toast_ok,
        final_js=FILES,
        tags=("toast", "timeout", "undo"),
    ),
]
# several widgets per task: more steps than the one-control fixtures
TASKS = [replace(t, max_steps=REAL_MAX_STEPS) for t in TASKS]

PROBES = [
    Probe(
        "f3-wizard-step",
        "{fixtures}/cov3/wizard.html",
        "Which step of the checkout is shown?",
        ["Step 1 of 3: Your details", "Step 2 of 3: Delivery", "Step 3 of 3: Review", "The order is placed"],
        "Step 1 of 3: Your details",
    ),
    Probe(
        "f3-wizard-price",
        "{fixtures}/cov3/wizard.html",
        "What is the price of the bouquet?",
        ["€39.00", "€45.00", "€6.00", "€33.00"],
        "€39.00",
    ),
    Probe("f3-masked-buy", "{fixtures}/cov3/masked.html", "Can the Buy tickets button be clicked now?", None, "NO"),
    Probe("f3-masked-qty", "{fixtures}/cov3/masked.html", "How many tickets are selected?", ["1", "2", "4", "6"], "1"),
    Probe("f3-spa-billing", "{fixtures}/cov3/spa.html", "Is there a Billing topic in the help center?", None, "YES"),
    Probe(
        "f3-xframe-stores",
        "{fixtures}/cov3/xframe.html",
        "How many stores does the store finder list?",
        ["3", "1", "5", "10"],
        "3",
    ),
    Probe(
        "f3-xframe-sol",
        "{fixtures}/cov3/xframe.html",
        "Until what time is the Sol store open?",
        ["21:00", "20:00", "20:30", "22:00"],
        "21:00",
    ),
    Probe("f3-scroll-57", "{fixtures}/cov3/scroll.html", "Is Product 57 shown on the page right now?", None, "NO"),
    Probe(
        "f3-table-page",
        "{fixtures}/cov3/table.html",
        "Which page of invoices is shown?",
        ["Page 1 of 6", "Page 2 of 6", "Page 6 of 6", "Page 1 of 3"],
        "Page 1 of 6",
    ),
    Probe("f3-table-overdue", "{fixtures}/cov3/table.html", "Is invoice INV-1001 overdue?", None, "YES"),
    Probe(
        "f3-cookie-reject",
        "{fixtures}/cov3/cookie.html",
        "Does the first screen of the cookie dialog have a button to reject cookies?",
        None,
        "NO",
    ),
    Probe("f3-inbox-sam", "{fixtures}/cov3/inbox.html", "Is the message from Sam Okafor starred?", None, "NO"),
    Probe(
        "f3-inbox-count",
        "{fixtures}/cov3/inbox.html",
        "How many messages are in the inbox?",
        ["4", "3", "2", "5"],
        "4",
    ),
    Probe(
        "f3-valid-disabled",
        "{fixtures}/cov3/validsubmit.html",
        "Can the Create workspace button be clicked now?",
        None,
        "NO",
    ),
    Probe(
        "f3-toast-deleted",
        "{fixtures}/cov3/toast.html",
        "Which file was just deleted?",
        ["report.pdf", "draft.txt", "photo.jpg", "budget-2026.xlsx"],
        "report.pdf",
    ),
]

# local pages: core. Extended until its fix is on main: f3-wizard (bench bug 22: told to go back, Jev uses GO_BACK, which
# leaves for the session's blank first page)
TASKS = ci_tier(TASKS, core={t.name for t in TASKS} - {"f3-wizard"})
PROBES = ci_tier(PROBES, core={p.name for p in PROBES})
