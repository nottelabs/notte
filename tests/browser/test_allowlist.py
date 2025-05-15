import asyncio
import os

import pytest
from notte_browser.session import NotteSessionConfig
from notte_core.browser.allowlist import ActionAllowList, URLAllowList
from notte_core.controller.actions import GotoAction, WaitAction

import notte


async def get_actions_by_allowlist(allowlist: ActionAllowList | None) -> list[str]:
    config = NotteSessionConfig().disable_perception().disable_web_security()

    if allowlist is not None:
        config = config.set_allow_list(allowlist)

    async with notte.Session(config=config) as session:
        file_path = "tests/data/duckduckgo.html"
        _ = await session.window.page.goto(url=f"file://{os.path.abspath(file_path)}")

        res = await session.act(WaitAction(time_ms=100))
        actions = res.space.actions()

        action_ids = [action.id for action in actions]

        return action_ids


@pytest.mark.asyncio
async def test_action_allow_list():
    # dont hide any action

    assert await get_actions_by_allowlist(None) == ["L1", "F1", "I1", "B1", "L2", "B2", "F2", "L3", "F3", "L4", "L5"]

    # hide the set as default search button / action
    assert await get_actions_by_allowlist(ActionAllowList().hide_by_text("Set As Default Search")) == [
        "L1",
        "F1",
        "I1",
        "B1",
        "L2",
        "B2",
        "F2",
        "F3",
        "L4",
        "L5",
    ]

    # hide images
    assert await get_actions_by_allowlist(ActionAllowList().hide_by_tag("img")) == [
        "L1",
        "I1",
        "B1",
        "L2",
        "B2",
        "L3",
        "L4",
        "L5",
    ]

    # hide by class
    assert await get_actions_by_allowlist(
        ActionAllowList().hide_by_class(
            "cta-cards_button__1dD9t button_button__GGtY1 button_primary__bqhFV button_size-sm__fklol"
        )
    ) == [
        "L1",
        "F1",
        "I1",
        "B1",
        "L2",
        "B2",
        "F2",
        "L3",
        "F3",
        "L5",
    ]

    assert await get_actions_by_allowlist(ActionAllowList().hide_by_id("searchbox_input")) == [
        "L1",
        "F1",
        "B1",
        "L2",
        "B2",
        "F2",
        "L3",
        "F3",
        "L4",
        "L5",
    ]

    assert await get_actions_by_allowlist(
        ActionAllowList()
        .hide_by_text("Set As Default Search")
        .hide_by_tag("img")
        .hide_by_class("cta-cards_button__1dD9t button_button__GGtY1 button_primary__bqhFV button_size-sm__fklol")
        .hide_by_id("searchbox_input")
    ) == [
        "L1",
        "B1",
        "L2",
        "B2",
        "L5",
    ]


def test_url_allow_list():
    url_filter = URLAllowList()

    # strict.com: everything but /public/4 is unacessible
    _ = url_filter.block("strict.com/*")  # All subdomains of malicious.com
    _ = url_filter.allow("strict.com/public/4")  # Specific section that is whitelisted

    assert not url_filter.is_allowed("https://strict.com/hello/dashboard")
    assert not url_filter.is_allowed("https://strict.com/haaa")
    assert url_filter.is_allowed("https://strict.com/public/4")

    # strict_reverse.com: everything is unnacessible
    _ = url_filter.allow("strict_reverse.com/public/4")  # Specific section that is whitelisted
    _ = url_filter.block("strict_reverse.com/*")  # All subdomains of malicious.com, overwrites

    assert not url_filter.is_allowed("https://strict_reverse.com/hello/dashboard")
    assert not url_filter.is_allowed("https://strict_reverse.com/haaa")
    assert not url_filter.is_allowed("https://strict_reverse.com/public/4")

    # example.com: everything is allowed but some pages per domain
    _ = url_filter.allow("example.com/*")  # All pages on example.com
    _ = url_filter.allow("*.example.com/*")  # All subdomains of example.com
    _ = url_filter.block("example.com/admin/*")  # Admin section of example.com
    _ = url_filter.block("*.example.com/private/*")  # Private section on any subdomain

    assert url_filter.is_allowed("https://example.com/page")
    assert url_filter.is_allowed("https://sub.example.com/page")
    assert url_filter.is_allowed("https://sub.example.com/category/search/term")
    assert url_filter.is_allowed("https://example.com/private/post")
    assert not url_filter.is_allowed("https://blog.example.com/private/post")
    assert not url_filter.is_allowed("https://example.com/admin/post")
    assert url_filter.is_allowed("https://blog.example.com/admin/post")

    # everything blocked
    _ = url_filter.block("malicious.com/*")
    _ = url_filter.block("*.malicious.com/*")  # All subdomains of malicious.com

    assert not url_filter.is_allowed("https://malicious.com/page")
    assert not url_filter.is_allowed("https://sub.malicious.com/page")

    # everything whitelisted
    _ = url_filter.allow("*.good.com/*")
    assert url_filter.is_allowed("https://good.com/page")
    assert url_filter.is_allowed("https://sub.good.com/page")

    # if domain not in whitelist, assume ok
    assert url_filter.is_allowed("https://not_matched.com/page")
    assert url_filter.is_allowed("https://sub.not_matched.com/page")

    # forgot to block subdomains:
    _ = url_filter.block("malicious_subs.com/*")
    assert not url_filter.is_allowed("https://malicious_subs.com/page")
    assert url_filter.is_allowed("https://sub.malicious_subs.com/page")

    # test with actual urls
    _ = url_filter.allow("google.com/*")
    _ = url_filter.block("images.google.com/*")
    assert url_filter.is_allowed("https://www.google.com/search?q=dogs")
    assert not url_filter.is_allowed("https://images.google.com/")

    # can allow one single url
    _ = url_filter.allow("google.com/*")
    _ = url_filter.block("images.google.com/*")
    _ = url_filter.allow("images.google.com/")
    assert url_filter.is_allowed("https://www.google.com/search?q=dogs")
    assert not url_filter.is_allowed("https://images.google.com/search?q=dogs")
    assert url_filter.is_allowed("https://images.google.com/")


@pytest.mark.asyncio
async def test_session_url_allowlist():
    url_filter = URLAllowList()
    _ = url_filter.allow("google.com/*")
    _ = url_filter.block("images.google.com/*")

    config = NotteSessionConfig().disable_perception().disable_web_security().set_url_allow_list(url_filter)

    # have to do this due to raising in playwright handler
    loop = asyncio.get_event_loop()
    exception_holder = []

    def exception_handler(loop, context):
        exception_holder.append(context["exception"])

    loop.set_exception_handler(exception_handler)

    async with notte.Session(config=config) as session:
        # can go to google
        _ = await session.act(GotoAction(url="https://www.google.com/search?q=dogs"))

        assert len(exception_holder) == 0

        # cant go to images.google
        _ = await session.act(GotoAction(url="https://images.google.com/"))

        assert len(exception_holder) == 1 and isinstance(exception_holder[0], ValueError)
