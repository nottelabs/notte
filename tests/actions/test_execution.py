import asyncio
from dataclasses import dataclass

import pytest
from notte_browser.session import NotteSession
from notte_core.common.config import PerceptionType
from notte_sdk.types import ExecutionRequest

from tests.mock.mock_service import MockLLMService
from tests.mock.mock_service import patch_llm_service as _patch_llm_service

patch_llm_service = _patch_llm_service


@pytest.fixture
def headless() -> bool:
    return True


@dataclass
class ExecutionTest:
    url: str
    steps: list[ExecutionRequest]


@pytest.fixture
def mock_llm_service() -> MockLLMService:
    return MockLLMService(mock_response="")


@pytest.fixture
def phantombuster_login() -> ExecutionTest:
    return ExecutionTest(
        url="https://phantombuster.com/login",
        steps=[
            ExecutionRequest(type="click", id="B4", value=None, enter=False),
            ExecutionRequest(type="fill", id="I1", value="lucasgiordano@gmail.com", enter=False),
            ExecutionRequest(type="fill", id="I2", value="lucasgiordano", enter=False),
            ExecutionRequest(type="click", id="B8", value=None, enter=False),
        ],
    )


async def _test_execution(test: ExecutionTest, headless: bool, patch_llm_service: MockLLMService) -> None:
    async with NotteSession(
        headless=headless,
    ) as page:
        _ = await page.aexecute(type="goto", value=test.url)
        _ = await page.aobserve(perception_type=PerceptionType.FAST)
        for step in test.steps:
            if step.id is not None and not page.snapshot.dom_node.find(step.id):
                inodes = [(n.id, n.text) for n in page.snapshot.interaction_nodes()]
                raise ValueError(f"Action {step.id} not found in context with interactions {inodes}")
            _ = await page.aexecute(**step.model_dump(exclude_none=True))
            _ = await page.aobserve(perception_type=PerceptionType.FAST)


def test_execution(phantombuster_login: ExecutionTest, headless: bool, patch_llm_service: MockLLMService) -> None:
    asyncio.run(_test_execution(phantombuster_login, headless, patch_llm_service))
