# pyright: basic
"""Local pages, round 2 (`fixtures/cov2/`): a virtualised list, "load more", a board reordered by drag and drop (not
supported: a clean BLOCKED passes) or by a card menu, a file picker (not supported either), nested and hover-only
menus, a code shown in a second tab, a form in a modal dialog, Japanese and Arabic (RTL) forms, a cookie wall that
hides its reject button, a chart dashboard, and search as you type with a debounce."""

import json
import re
from dataclasses import replace
from typing import Any

from ..model import REAL_MAX_STEPS, Probe, Task, ci_tier, last_status, one, path


def _page(page: str, **expected: str):
    def check(f: dict[str, Any], _: dict[str, Any]) -> bool:
        return path(f).endswith("/cov2/" + page) and all(one(f["url"], k) == v for k, v in expected.items())

    return check


def _blocked_on(page: str, f: dict[str, Any], run: dict[str, Any]) -> bool:
    """A clean BLOCKED: the runner said it cannot do it, and left the start page without submitting anything."""
    return last_status(run) == "blocked" and path(f).endswith("/cov2/" + page)


BOARD = """JSON.stringify({backlog: [...document.querySelectorAll('#backlog > li')].map(li => li.textContent.trim()),
  sprint: [...document.querySelectorAll('#sprint > li')].map(li => li.dataset.name)})"""
BACKLOG = ["Update the docs", "Fix the login timeout", "Write tests", "Review the API"]
SPRINT = ["Design the settings page", "Migrate the database", "Deploy", "Retro notes"]


def _drag_ok(f: dict[str, Any], run: dict[str, Any]) -> bool:
    board = f.get("extra") or {}
    if board.get("backlog") == ["Write tests", "Update the docs", "Fix the login timeout", "Review the API"]:
        return board.get("sprint") == SPRINT
    # drag and drop is not an act operation: say so, and leave the board as it is
    return _blocked_on("kanban.html", f, run) and board == {"backlog": BACKLOG, "sprint": SPRINT}


def _menu_move_ok(f: dict[str, Any], _: dict[str, Any]) -> bool:
    board = f.get("extra") or {}
    return board.get("backlog") == BACKLOG and board.get("sprint") == [
        "Deploy",
        "Design the settings page",
        "Migrate the database",
        "Retro notes",
    ]


def _upload_ok(f: dict[str, Any], run: dict[str, Any]) -> bool:
    # there is no file to pick and no upload operation: a clean BLOCKED, the profile not saved
    return _blocked_on("upload.html", f, run)


def _hover_menu_ok(f: dict[str, Any], run: dict[str, Any]) -> bool:
    # the Company menu opens on mouse hover only: reaching Careers, or saying it cannot, both pass
    return _page("careers.html", **{"from": "menu"})(f, run) or _blocked_on("menu.html", f, run)


def _rtl_ok(f: dict[str, Any], _: dict[str, Any]) -> bool:
    u = f["url"]
    return (
        path(f).endswith("/cov2/rtl-done.html")
        and (one(u, "name") or "").strip() == "ليلى حسن"
        and re.sub(r"\D", "", one(u, "phone") or "") == "01001234567"
        and one(u, "city") == "alexandria"
        and one(u, "slot") == "evening"
    )


def _cookies_refused(f: dict[str, Any], _: dict[str, Any]) -> bool:
    try:
        consent = json.loads(f.get("consent") or "null")
    except ValueError:
        return False
    refused = consent == {"analytics": False, "ads": False, "personal": False}
    return path(f).endswith("/cov2/pricing.html") and refused


GOAL_JA = "氏名「山田太郎」、フリガナ「ヤマダタロウ」、郵便番号「530-0001」、都道府県「大阪府」で会員登録してください。"
GOAL_AR = "اطلب توصيلًا باسم «ليلى حسن» ورقم الهاتف 01001234567 إلى الإسكندرية في المساء."

TASKS = [
    Task(
        "f2-vlist",
        "{fixtures}/cov2/vlist.html",
        "Open order #10237.",
        _page("order.html", id="10237"),
        tags=("virtualised-list", "scroll-container"),
    ),
    Task(
        "f2-loadmore",
        "{fixtures}/cov2/loadmore.html",
        "Open order #1037.",
        _page("order.html", id="1037"),
        tags=("load-more",),
    ),
    Task(
        "f2-kanban-drag",
        "{fixtures}/cov2/kanban.html",
        "In the Backlog list, move 'Write tests' to the top.",
        _drag_ok,
        final_js=BOARD,
        tags=("drag-and-drop", "capability"),
    ),
    Task(
        "f2-kanban-menu",
        "{fixtures}/cov2/kanban.html",
        "In the Sprint list, move 'Deploy' to the top.",
        _menu_move_ok,
        final_js=BOARD,
        tags=("sortable", "menu-button"),
    ),
    Task(
        "f2-upload",
        "{fixtures}/cov2/upload.html",
        "Upload the photo /tmp/notte-avatar.png as the profile photo and save the profile.",
        _upload_ok,
        tags=("file-picker", "capability"),
    ),
    Task(
        "f2-menu-nested",
        "{fixtures}/cov2/menu.html",
        "Switch the app to the dark theme from the Settings menu.",
        _page("menu-done.html", theme="dark"),
        tags=("menu", "nested-menu"),
    ),
    Task(
        "f2-menu-hover",
        "{fixtures}/cov2/menu.html",
        "Open the Careers page from the Company menu.",
        _hover_menu_ok,
        tags=("hover-menu", "capability"),
    ),
    Task(
        "f2-multitab",
        "{fixtures}/cov2/multitab.html",
        "Create an account for jane.doe@example.com with the verification code from the help page.",
        _page("verify-done.html", email="jane.doe@example.com", code="4821"),
        tags=("multi-tab", "new-tab", "window-close"),
    ),
    Task(
        "f2-dialog",
        "{fixtures}/cov2/dialogform.html",
        "Add Ana Silva (ana.silva@example.com) to the team as an Editor, then save the team.",
        _page("team-saved.html", members="Lars Berg:lars@northwind.test:admin;Ana Silva:ana.silva@example.com:editor"),
        tags=("dialog", "form", "select"),
    ),
    Task(
        "f2-cjk",
        "{fixtures}/cov2/cjk.html",
        GOAL_JA,
        _page("cjk-done.html", name="山田太郎", kana="ヤマダタロウ", zip="530-0001", pref="osaka"),
        tags=("ja", "cjk-input", "select"),
    ),
    Task("f2-rtl", "{fixtures}/cov2/rtl.html", GOAL_AR, _rtl_ok, tags=("ar", "rtl-input", "radio")),
    Task(
        "f2-darkcookie",
        "{fixtures}/cov2/darkcookie.html",
        "Refuse all optional cookies, then open the Pricing page.",
        _cookies_refused,
        tags=("consent", "dark-pattern", "modal"),
    ),
    Task(
        "f2-dashboard",
        "{fixtures}/cov2/dashboard.html",
        "Switch the dashboard to 2025, then open the details of the month with the most sign-ups.",
        _page("month.html", year="2025", month="7"),
        tags=("chart", "svg", "select"),
    ),
    Task(
        "f2-debounce",
        "{fixtures}/cov2/debounce.html",
        "Find the travel guide for Lisbon and open it.",
        _page("guide.html", id="lisbon"),
        tags=("search-as-you-type", "debounce"),
    ),
]
# several widgets per task: more steps than the one-control fixtures
TASKS = [replace(t, max_steps=REAL_MAX_STEPS) for t in TASKS]

PROBES = [
    Probe("f2-vlist-shown", "{fixtures}/cov2/vlist.html", "Is order #10237 shown on the page right now?", None, "NO"),
    Probe(
        "f2-loadmore-count",
        "{fixtures}/cov2/loadmore.html",
        "How many orders are listed?",
        ["10", "20", "60", "5"],
        "10",
    ),
    Probe(
        "f2-kanban-top",
        "{fixtures}/cov2/kanban.html",
        "Which card is at the top of the Sprint list?",
        ["Design the settings page", "Deploy", "Retro notes", "Update the docs"],
        "Design the settings page",
    ),
    Probe("f2-upload-chosen", "{fixtures}/cov2/upload.html", "Has a profile photo been chosen?", None, "NO"),
    Probe("f2-menu-open", "{fixtures}/cov2/menu.html", "Is the Settings menu open?", None, "NO"),
    Probe(
        "f2-multitab-code", "{fixtures}/cov2/multitab.html", "Is the verification code shown on this page?", None, "NO"
    ),
    Probe("f2-dialog-open", "{fixtures}/cov2/dialogform.html", "Is the add-member dialog open?", None, "NO"),
    Probe(
        "f2-cjk-pref",
        "{fixtures}/cov2/cjk.html",
        "Which prefecture is selected?",
        ["東京都", "大阪府", "北海道", "京都府"],
        "東京都",
    ),
    Probe(
        "f2-rtl-city",
        "{fixtures}/cov2/rtl.html",
        "Which city is selected for the delivery?",
        ["Cairo", "Alexandria", "Giza", "Luxor"],
        "Cairo",
    ),
    Probe(
        "f2-darkcookie-reject",
        "{fixtures}/cov2/darkcookie.html",
        "Does the cookie banner itself have a button to reject cookies?",
        None,
        "NO",
    ),
    Probe(
        "f2-dashboard-churn",
        "{fixtures}/cov2/dashboard.html",
        "What is the churn rate?",
        ["2.1%", "2.8%", "1.2%", "21%"],
        "2.1%",
    ),
    Probe(
        "f2-dashboard-max",
        "{fixtures}/cov2/dashboard.html",
        "In which month were there the most sign-ups?",
        ["January", "March", "July", "September"],
        "March",
    ),
    Probe("f2-dashboard-revenue", "{fixtures}/cov2/dashboard.html", "Is the revenue above €1M?", None, "YES"),
    Probe("f2-debounce-results", "{fixtures}/cov2/debounce.html", "Are any search results shown?", None, "NO"),
]

# local pages: core, except those that fail on a bug no fix is in flight for yet (bench bug list), to move to core
# when it lands: f2-vlist (13: SCROLL does not reach an inner scroller), f2-dashboard and f2-dashboard-max (14: SVG
# chart content is not observed), f2-multitab (act keeps no value read on an earlier page: a design question)
TASKS = ci_tier(TASKS, core={t.name for t in TASKS} - {"f2-vlist", "f2-dashboard", "f2-multitab"})
PROBES = ci_tier(PROBES, core={p.name for p in PROBES} - {"f2-dashboard-max"})
