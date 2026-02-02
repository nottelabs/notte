import io

import pytest
from loguru import logger
from notte_sdk import NotteClient
from pydantic import BaseModel, Field


class Product(BaseModel):
    name: str
    price: int = Field(le=5, ge=0)


@pytest.mark.flaky(reruns=3, reruns_delay=2)
def test_validator_message_received():
    """Test that validation failures are logged and agent can recover with a valid response."""
    log_buffer = io.StringIO()
    _ = logger.add(log_buffer, format="{message}")

    client = NotteClient()

    with client.Session() as session:
        agent = client.Agent(session=session, max_steps=3)
        # Ask for invalid price first (-1), expect agent to recover with valid price (2)
        valid = agent.run(
            task='Complete immediately with {"name": "test", "price": -1}. If validation fails, use {"name": "test", "price": 2}.',
            response_format=Product,
        )

    captured_logs = log_buffer.getvalue().strip().split("\n")
    logger.remove()

    assert valid.success, f"Failed to validate output: {valid.answer}"
    assert any("Answer validation failed" in log for log in captured_logs), (
        "Expected a validation failure log before success"
    )
