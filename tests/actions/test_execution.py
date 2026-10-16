import asyncio
from dataclasses import dataclass

import pytest
from notte_browser.session import NotteSession
from notte_sdk.types import ExecutionRequest


@pytest.fixture
def headless() -> bool:
    return True


@dataclass
class ExecutionTest:
    url: str
    steps: list[ExecutionRequest]


@pytest.fixture
def phantombuster_login() -> ExecutionTest:
    return ExecutionTest(
        url="https://phantombuster.com/login",
        steps=[
            ExecutionRequest(type="click", id="B4", value=None, enter=False),
            ExecutionRequest(type="fill", id="I1", value="lucasgiordano@gmail.com", enter=False),
            ExecutionRequest(type="fill", id="I2", value="lucasgiordano", enter=False),
            ExecutionRequest(type="click", id="B2", value=None, enter=False),
        ],
    )


async def _test_execution(test: ExecutionTest, headless: bool) -> None:
    async with NotteSession(
        headless=headless,
    ) as page:
        _ = await page.aexecute(type="goto", url=test.url)
        _ = await page.aobserve()
        for step in test.steps:
            if step.id is not None and not page.snapshot.dom_node.find(step.id):
                inodes = [(n.id, n.text) for n in page.snapshot.interaction_nodes()]
                raise ValueError(f"Action {step.id} not found in context with interactions {inodes}")
            _ = await page.aexecute(**step.model_dump(exclude_none=True))
            _ = await page.aobserve()


@pytest.mark.live
def test_execution(phantombuster_login: ExecutionTest, headless: bool) -> None:
    asyncio.run(_test_execution(phantombuster_login, headless))
