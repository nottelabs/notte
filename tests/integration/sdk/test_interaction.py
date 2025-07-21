import pytest
from notte_core.actions import ClickAction
from notte_core.browser.observation import ExecutionResult
from notte_core.common.config import PerceptionType
from notte_sdk.client import NotteClient


@pytest.mark.asyncio
async def test_sdk_special_action_validation():
    client = NotteClient()
    """Test validation of special action parameters"""
    with client.Session(headless=True) as page:
        _ = page.execute(type="goto", value="https://github.com/")
        _ = page.observe(perception_type=PerceptionType.FAST)
        # Test S1 requires URL parameter
        with pytest.raises(ValueError, match="validation error for GotoAction"):
            _ = page.execute(type="goto")

        # Test S7 requires wait time parameter
        with pytest.raises(ValueError, match="validation error for WaitAction"):
            _ = page.execute(type="wait")

        def check_failure(result: ExecutionResult) -> None:
            assert not result.success
            assert isinstance(result.exception, ValueError)
            assert "Action with id 'X1' is invalid" in result.message

        # Test invalid special action, multi combinations
        result = page.execute(type="click", action_id="X1")
        check_failure(result)

        result = page.execute(ClickAction(id="X1"))
        check_failure(result)
