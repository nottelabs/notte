import os

import pytest
from notte_core.actions import ScrapeAction

import notte


@pytest.mark.asyncio
async def test_alert():
    async with notte.Session(
        headless=True, enable_perception=False, viewport_width=1280, viewport_height=720
    ) as session:
        file_path = "tests/data/dialog_test.html"
        _ = await session.aobserve(url="https://google.com")
        _ = await session.window.page.goto(url=f"file://{os.path.abspath(file_path)}")

        _ = notte.Agent(session=session).run(
            task="""CRITICAL: DONT USE GOTO. Your first action has to be a wait action. On the current page, click on the "show alert" button, and dismiss it.""",
            # task="""log in at https://codeshare.io/codes""",
        )
        res = session.observe()
        res = session.step(ScrapeAction())
        res = session.observe()

        assert res.data is not None
        assert res.data.markdown is not None
        assert "Alert was dismissed" in res.data.markdown


@pytest.mark.asyncio
async def test_dismiss():
    async with notte.Session(
        headless=True, enable_perception=False, viewport_width=1280, viewport_height=720
    ) as session:
        file_path = "tests/data/dialog_test.html"
        _ = await session.aobserve(url="https://google.com")
        _ = await session.window.page.goto(url=f"file://{os.path.abspath(file_path)}")

        _ = notte.Agent(session=session).run(
            task="""CRITICAL: DONT USE GOTO. Your first action has to be a wait action. On the current page, click on the "show confirm" button, and dismiss it.""",
            # task="""log in at https://codeshare.io/codes""",
        )
        res = session.observe()
        res = session.step(ScrapeAction())
        res = session.observe()

        assert res.data is not None
        assert res.data.markdown is not None
        assert "Cancel clicked" in res.data.markdown


@pytest.mark.asyncio
async def test_confirm():
    async with notte.Session(
        headless=True, enable_perception=False, viewport_width=1280, viewport_height=720
    ) as session:
        file_path = "tests/data/dialog_test.html"
        _ = await session.aobserve(url="https://google.com")
        _ = await session.window.page.goto(url=f"file://{os.path.abspath(file_path)}")

        _ = notte.Agent(session=session).run(
            task="""CRITICAL: DONT USE GOTO. Your first action has to be a wait action. On the current page, click on the "show confirm" button, and accept it.""",
            # task="""log in at https://codeshare.io/codes""",
        )
        res = session.observe()
        res = session.step(ScrapeAction())
        res = session.observe()

        assert res.data is not None
        assert res.data.markdown is not None
        assert "OK clicked" in res.data.markdown


@pytest.mark.asyncio
async def test_prompt():
    async with notte.Session(
        headless=True, enable_perception=False, viewport_width=1280, viewport_height=720
    ) as session:
        file_path = "tests/data/dialog_test.html"
        _ = await session.aobserve(url="https://google.com")
        _ = await session.window.page.goto(url=f"file://{os.path.abspath(file_path)}")

        _ = notte.Agent(session=session).run(
            task="""CRITICAL: DONT USE GOTO. Your first action has to be a wait action. On the current page, click on the "show prompt" button, and answer the input with the info you got from the dialog""",
            # task="""log in at https://codeshare.io/codes""",
        )
        res = session.observe()
        res = session.step(ScrapeAction())
        res = session.observe()

        assert res.data is not None
        assert res.data.markdown is not None
        assert "marcello" in res.data.markdown
