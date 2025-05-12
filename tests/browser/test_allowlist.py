import os

import pytest
from notte_browser.session import NotteSessionConfig
from notte_core.browser.allowlist import ActionAllowList, URLAllowList
from notte_core.controller.actions import WaitAction

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


# @pytest.mark.skip(reason="Loading the html only works in headful?")
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
    url_filter.add_to_blocklist("strict.com/*")  # All subdomains of malicious.com
    url_filter.add_to_allowlist("strict.com/public/4")  # Specific section that is whitelisted

    assert not url_filter.is_allowed("https://strict.com/hello/dashboard")
    assert not url_filter.is_allowed("https://strict.com/haaa")
    assert url_filter.is_allowed("https://strict.com/public/4")

    # strict_reverse.com: everything is unnacessible
    url_filter.add_to_allowlist("strict_reverse.com/public/4")  # Specific section that is whitelisted
    url_filter.add_to_blocklist("strict_reverse.com/*")  # All subdomains of malicious.com, overwrites

    assert not url_filter.is_allowed("https://strict_reverse.com/hello/dashboard")
    assert not url_filter.is_allowed("https://strict_reverse.com/haaa")
    assert not url_filter.is_allowed("https://strict_reverse.com/public/4")

    # example.com: everything is allowed but some pages per domain
    url_filter.add_to_allowlist("example.com/*")  # All pages on example.com
    url_filter.add_to_allowlist("*.example.com/*")  # All subdomains of example.com
    url_filter.add_to_blocklist("example.com/admin/*")  # Admin section of example.com
    url_filter.add_to_blocklist("*.example.com/private/*")  # Private section on any subdomain

    assert url_filter.is_allowed("https://example.com/page")
    assert url_filter.is_allowed("https://sub.example.com/page")
    assert url_filter.is_allowed("https://sub.example.com/category/search/term")
    assert url_filter.is_allowed("https://example.com/private/post")
    assert not url_filter.is_allowed("https://blog.example.com/private/post")
    assert not url_filter.is_allowed("https://example.com/admin/post")
    assert url_filter.is_allowed("https://blog.example.com/admin/post")

    # everything blocked
    url_filter.add_to_blocklist("malicious.com/*")
    url_filter.add_to_blocklist("*.malicious.com/*")  # All subdomains of malicious.com

    assert not url_filter.is_allowed("https://malicious.com/page")
    assert not url_filter.is_allowed("https://sub.malicious.com/page")

    # everything whitelisted
    url_filter.add_to_allowlist("*.good.com/*")
    assert url_filter.is_allowed("https://good.com/page")
    assert url_filter.is_allowed("https://sub.good.com/page")

    # if domain not in whitelist, assume ok
    assert url_filter.is_allowed("https://not_matched.com/page")
    assert url_filter.is_allowed("https://sub.not_matched.com/page")

    # forgot to block subdomains:
    url_filter.add_to_blocklist("malicious_subs.com/*")
    assert not url_filter.is_allowed("https://malicious_subs.com/page")
    assert url_filter.is_allowed("https://sub.malicious_subs.com/page")
