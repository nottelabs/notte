import asyncio
from dataclasses import dataclass

import pytest
from notte_browser.session import NotteSession
from notte_sdk.types import ExecutionRequest


@pytest.fixture
def headless() -> bool:
    return True


@dataclass
class Step:
    type: str
    # the element is found by its text: ids change with what the page shows (a cookie banner or not)
    text: str
    value: str | None = None
    # skipped when the page does not show the element
    optional: bool = False


@dataclass
class ExecutionTest:
    url: str
    steps: list[Step]


@pytest.fixture
def phantombuster_login() -> ExecutionTest:
    return ExecutionTest(
        url="https://phantombuster.com/login",
        steps=[
            # the cookie banner is shown to some visitors only
            Step(type="click", text="Close banner", optional=True),
            Step(type="fill", text="email", value="lucasgiordano@gmail.com"),
            Step(type="fill", text="password", value="lucasgiordano"),
            Step(type="click", text="Log in"),
        ],
    )


async def _test_execution(test: ExecutionTest, headless: bool) -> None:
    async with NotteSession(
        headless=headless,
    ) as page:
        _ = await page.aexecute(type="goto", url=test.url)
        _ = await page.aobserve()
        for step in test.steps:
            inodes = [(n.id, n.text) for n in page.snapshot.interaction_nodes()]
            ids = [id for id, text in inodes if text == step.text]
            if not ids:
                if step.optional:
                    continue
                raise ValueError(f"No element {step.text!r} in context with interactions {inodes}")
            request = ExecutionRequest(type=step.type, id=ids[0], value=step.value, enter=False)
            _ = await page.aexecute(**request.model_dump(exclude_none=True))
            _ = await page.aobserve()


@pytest.mark.live
def test_execution(phantombuster_login: ExecutionTest, headless: bool) -> None:
    asyncio.run(_test_execution(phantombuster_login, headless))
