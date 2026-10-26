# pyright: basic
"""Tasks and probes on public demo and test sites (the-internet, books.toscrape, TodoMVC, Selenium's web form,
Wikipedia): small, stable pages, plus the `done` and `impossible` tasks that must not act."""

from typing import Any

from ..model import NEUTRAL_OPERATIONS, Probe, Task, checkboxes, executed, last_status, one, path, qs


def _webform_ok(f: dict[str, Any], _: dict[str, Any]) -> bool:
    u = f["url"]
    return (
        path(f).endswith("/submitted-form.html")
        and one(u, "my-text") == "notte bench"
        and one(u, "my-select") == "2"
        and len(qs(u).get("my-check", [])) == 2
    )


def _todos_ok(f: dict[str, Any], _: dict[str, Any]) -> bool:
    todos = {t["text"].lower(): t["done"] for t in f.get("todos") or []}
    return todos == {"buy milk": True, "walk the dog": False}


def _already_done_ok(f: dict[str, Any], run: dict[str, Any]) -> bool:
    # checkbox 2 is checked when the page loads: answer DONE without acting
    return (
        path(f) == "/checkboxes" and checkboxes(f) == [False, True] and not executed(run) and last_status(run) == "done"
    )


def _impossible_ok(f: dict[str, Any], run: dict[str, Any]) -> bool:
    # the page has no Google sign-in: answer BLOCKED, and type or click nothing on the way
    fields = [i for i in f.get("inputs") or [] if i["type"] in ("text", "password")]
    return (
        path(f) == "/login"
        and all(not i["value"] for i in fields)
        and all(op in NEUTRAL_OPERATIONS for op in executed(run))
        and last_status(run) == "blocked"
    )


def _dynamic_ok(f: dict[str, Any], _: dict[str, Any]) -> bool:
    texts = [i for i in f.get("inputs") or [] if i["type"] == "text"]
    return path(f) == "/dynamic_controls" and any(i["value"] == "hello" and not i["disabled"] for i in texts)


TASKS = [
    Task(
        "wikipedia",
        "https://en.wikipedia.org/wiki/Main_Page",
        "Search Wikipedia for Ada Lovelace and open her article.",
        lambda f, _: path(f) == "/wiki/Ada_Lovelace",
    ),
    Task(
        "webform",
        "https://www.selenium.dev/selenium/web/web-form.html",
        "Type 'notte bench' in the text input, select Two in the dropdown (select), also check the "
        "Default checkbox (keep the Checked checkbox checked), then submit the form.",
        _webform_ok,
    ),
    Task(
        "todomvc",
        "https://todomvc.com/examples/react/dist/",
        "Add two todos, 'buy milk' and 'walk the dog', then mark 'buy milk' as completed.",
        _todos_ok,
    ),
    Task(
        "login",
        "https://the-internet.herokuapp.com/login",
        "Log in with username tomsmith and password SuperSecretPassword!",
        lambda f, _: path(f) == "/secure",
    ),
    Task(
        "books",
        "https://books.toscrape.com/",
        "Open the Poetry category, then open the book 'Howl and Other Poems'.",
        lambda f, _: path(f) == "/catalogue/howl-and-other-poems_522/index.html",
        tags=("multi-page",),
    ),
    Task(
        "dynamic",
        "https://the-internet.herokuapp.com/dynamic_controls",
        "Enable the text input, then type hello in it.",
        _dynamic_ok,
        tags=("wait",),
    ),
    Task(
        "already-done",
        "https://the-internet.herokuapp.com/checkboxes",
        "Make sure checkbox 2 is checked.",
        _already_done_ok,
        tags=("done",),
    ),
    Task(
        "impossible",
        "https://the-internet.herokuapp.com/login",
        "Log in with your Google account.",
        _impossible_ok,
        tags=("blocked",),
    ),
]

BOOK = "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
PROBES = [
    # ---- choose()
    Probe("price", BOOK, "What is the price of this book?", ["£51.77", "£53.74", "£50.10", "£47.82"], "£51.77"),
    Probe("stock-count", BOOK, "How many copies are available?", ["5", "19", "22", "None"], "22"),
    Probe(
        "which-checked",
        "https://the-internet.herokuapp.com/checkboxes",
        "Which checkboxes are checked?",
        ["Only checkbox 1", "Only checkbox 2", "Both", "Neither"],
        "Only checkbox 2",
    ),
    Probe(
        "first-author",
        "https://quotes.toscrape.com/",
        "Who is the author of the first quote on the page?",
        ["Albert Einstein", "J.K. Rowling", "Jane Austen", "Marilyn Monroe"],
        "Albert Einstein",
    ),
    Probe(
        "username-hint",
        "https://the-internet.herokuapp.com/login",
        "Which username does the page tell you to use?",
        ["tomsmith", "admin", "SuperSecretPassword!", "guest"],
        "tomsmith",
    ),
    Probe(
        "button-label",
        "https://the-internet.herokuapp.com/dynamic_controls",
        "What does the button next to the text input say?",
        ["Enable", "Disable", "Remove", "Add"],
        "Enable",
    ),
    Probe(
        "century",
        "https://en.wikipedia.org/wiki/Ada_Lovelace",
        "In which century was the subject of this article born?",
        ["17th", "18th", "19th", "20th"],
        "19th",
    ),
    Probe(
        "star-rating",
        BOOK,
        # only drawn as stars (a CSS class): not in the page text, so a calibrated decider should be unsure
        "How many stars is this book rated?",
        ["One", "Two", "Three", "Four", "Five"],
        "Three",
    ),
    Probe(
        "webform-select",
        "https://www.selenium.dev/selenium/web/web-form.html",
        "Which option is currently selected in the dropdown (select)?",
        ["Open this select menu", "One", "Two", "Three"],
        "Open this select menu",
    ),
    # ---- check()
    Probe("logged-in", "https://the-internet.herokuapp.com/login", "Is the user logged in?", None, "NO"),
    Probe("in-stock", BOOK, "Is this book in stock?", None, "YES"),
    Probe("cb1-checked", "https://the-internet.herokuapp.com/checkboxes", "Is checkbox 1 checked?", None, "NO"),
    Probe("cb2-checked", "https://the-internet.herokuapp.com/checkboxes", "Is checkbox 2 checked?", None, "YES"),
    Probe(
        "input-enabled", "https://the-internet.herokuapp.com/dynamic_controls", "Is the text input enabled?", None, "NO"
    ),
    Probe(
        "ada-article",
        "https://en.wikipedia.org/wiki/Ada_Lovelace",
        "Is this the Wikipedia article about Ada Lovelace?",
        None,
        "YES",
    ),
    Probe("login-link", "https://quotes.toscrape.com/", "Is there a login link on this page?", None, "YES"),
    Probe("next-link", "https://quotes.toscrape.com/", "Is there a link to the next page of quotes?", None, "YES"),
    Probe("poetry-book", BOOK, "Is this book in the Poetry category?", None, "YES"),
    Probe("cb2-unchecked", "https://the-internet.herokuapp.com/checkboxes", "Is checkbox 2 unchecked?", None, "NO"),
    Probe(
        "default-checked",
        "https://www.selenium.dev/selenium/web/web-form.html",
        "Is the 'Default checkbox' checked?",
        None,
        "NO",
    ),
    Probe("five-stars", BOOK, "Is this book rated five stars?", None, "NO"),
    Probe("todos-any", "https://todomvc.com/examples/react/dist/", "Are there any todos in the list?", None, "NO"),
]
