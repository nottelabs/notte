import difflib
import json
from pathlib import Path
from typing import Any, Literal
from unittest.mock import patch

import pytest
from freezegun import freeze_time
from litellm import AllMessageValues
from notte_agent.common.validator import CompletionValidation
from notte_agent.falco.agent import FalcoAgent
from notte_browser.session import NotteSession
from notte_core.actions import (
    ClickAction,
    CompletionAction,
    FillAction,
    GotoAction,
    ScrapeAction,
    ScrollDownAction,
)
from notte_core.agent_types import AgentState, AgentStepResponse, RelevantInteraction
from notte_core.browser.observation import StepResult

DIR = Path(__file__).parent
MESSAGES_FILE = DIR / "reference_messages.json"
OUTPUT_MESSAGES_FILE = DIR / "output_messages.json"


# ANSI color codes
RED = "\033[91m"
GREEN = "\033[92m"
RESET = "\033[0m"


def assert_strings_equal(actual: str, expected: str, msg: str = "") -> None:
    """Assert that two strings are equal with a detailed colored diff on failure."""
    if actual != expected:
        diff = list(
            difflib.unified_diff(
                expected.splitlines(keepends=True),
                actual.splitlines(keepends=True),
                fromfile="expected",
                tofile="actual",
                lineterm="",
            )
        )

        # Add colors to the diff output
        colored_diff = []
        for line in diff:
            if line.startswith("+"):
                colored_diff.append(f"{GREEN}{line}{RESET}")
            elif line.startswith("-"):
                colored_diff.append(f"{RED}{line}{RESET}")
            else:
                colored_diff.append(line)

        diff_text = "\n".join(colored_diff)
        raise AssertionError(f"{msg}\nDiff:\n{diff_text}")


class MockLLMEngine:
    """Mock LLM engine that returns a predefined sequence of AgentStepResponse"""

    def __init__(self, sequence: list[AgentStepResponse]):
        self.sequence = sequence
        self.call_count = 0

    async def structured_completion(
        self, messages: list[Any], response_format: type[AgentStepResponse], use_strict_response_format: bool = False
    ) -> AgentStepResponse:
        """Return the next response in the sequence"""
        if self.call_count >= len(self.sequence):
            # If we run out of responses, return a completion action
            return AgentStepResponse(
                state=AgentState(
                    previous_goal_status="success",
                    previous_goal_eval="Task completed successfully",
                    page_summary="Final page reached",
                    relevant_interactions=[],
                    memory="Task completed",
                    next_goal="Complete the task",
                ),
                action=CompletionAction(
                    success=True,
                    answer="Task completed successfully",
                ),
            )

        response = self.sequence[self.call_count]
        self.call_count += 1
        return response


class MockValidator:
    """Mock validator that always returns success"""

    async def validate_old(
        self,
        task: str,
        output: CompletionAction,
        history: Any,
        response_format: Any = None,
    ) -> CompletionValidation:
        """Always return a successful validation"""
        return CompletionValidation(
            is_valid=True,
            reason="Mock validator always returns success for testing purposes",
        )

    async def validate(
        self,
        task: str,
        output: CompletionAction,
        history: Any,
        response_format: Any = None,
    ) -> StepResult:
        """Always return a successful validation"""
        return StepResult(
            success=True,
            message="Mock validator always returns success for testing purposes",
        )


class MockLLMService:
    def clip_tokens(document: str, max_tokens: int | None = None) -> str:
        return document

    async def structured_completion(*args, **kwargs):
        """Mock structured completion for scraping that returns a predefined response"""
        from notte_core.data.space import DictBaseModel, StructuredData

        # Create a mock response that matches the expected structure
        mock_data = DictBaseModel(root={"company_name": "Notte"})
        return StructuredData(success=True, data=mock_data, error=None)


def create_agent_step_response(
    action: Any,
    page_summary: str = "Current page",
    previous_goal_status: Literal["success", "failure", "unknown"] = "unknown",
    previous_goal_eval: str = "Evaluating current state",
    memory: str = "Remembering previous actions",
    next_goal: str = "Continue with next action",
    relevant_interactions: list[RelevantInteraction] | None = None,
) -> AgentStepResponse:
    """Helper function to create AgentStepResponse with default values"""
    if relevant_interactions is None:
        relevant_interactions = []

    return AgentStepResponse(
        state=AgentState(
            previous_goal_status=previous_goal_status,
            previous_goal_eval=previous_goal_eval,
            page_summary=page_summary,
            relevant_interactions=relevant_interactions,
            memory=memory,
            next_goal=next_goal,
        ),
        action=action,
    )


@pytest.mark.asyncio
async def test_falco_agent_consistent_trajectory():
    """Test that Falco agent follows a consistent trajectory with patched LLM"""

    # Define the sequence of actions as specified
    sequence = [
        # Step 1: goto: url=notte.cc
        create_agent_step_response(
            action=GotoAction(url="https://console.notte.cc"),
            page_summary="Navigating to notte.cc",
            next_goal="Navigate to the website",
        ),
        # Step 2: fill: "I1" hello@notte.c
        create_agent_step_response(
            action=FillAction(id="I1", value="hello@notte.c"),
            page_summary="On notte.cc homepage",
            previous_goal_status="success",
            previous_goal_eval="Successfully navigated to notte.cc",
            memory="Navigated to notte.cc",
            next_goal="Fill the email input field",
            relevant_interactions=[RelevantInteraction(id="I1", reason="Email input field")],
        ),
        # Step 3: click B1
        create_agent_step_response(
            action=ClickAction(id="B1"),
            page_summary="Email field filled",
            previous_goal_status="success",
            previous_goal_eval="Successfully filled email field",
            memory="Filled email field with hello@notte.c",
            next_goal="Click the submit button",
            relevant_interactions=[RelevantInteraction(id="B1", reason="Submit button")],
        ),
        # Step 4: scroll down
        create_agent_step_response(
            action=ScrollDownAction(amount=None),
            page_summary="Button clicked, page loaded",
            previous_goal_status="success",
            previous_goal_eval="Successfully clicked submit button",
            memory="Clicked submit button after filling email",
            next_goal="Scroll down to see more content",
        ),
        # Step 5: scrape with instruction "scrape the company name"
        create_agent_step_response(
            action=ScrapeAction(instructions="scrape the company name"),
            page_summary="Scrolled down, content visible",
            previous_goal_status="success",
            previous_goal_eval="Successfully scrolled down",
            memory="Scrolled down to view content",
            next_goal="Extract company name from the page",
        ),
    ]

    # Create mock LLM engine
    mock_llm = MockLLMEngine(sequence)

    # Create mock validator
    mock_validator = MockValidator()

    # Use real browser session
    async with NotteSession(headless=True, enable_perception=False) as session:
        # Create Falco agent
        agent = FalcoAgent(
            window=session.window,
            max_steps=10,
        )

        # Patch the LLM engine and validator
        with (
            patch.object(agent, "llm", mock_llm),
            patch.object(agent, "validator", mock_validator),
            patch.object(agent.session._data_scraping_pipe.schema_pipe, "llmserve", MockLLMService),
        ):
            # Run the agent
            response = await agent.run(task="Test consistent trajectory")

            # Verify the response
            assert response is not None
            assert response.success is True
            assert "Task completed successfully" in response.answer

            # Verify the trajectory has the expected number of steps
            assert len(response.trajectory) == 5

            # Verify each step in the trajectory
            trajectory_actions = [step.action for step in response.trajectory]

            # Check that the actions match our expected sequence
            assert isinstance(trajectory_actions[0], GotoAction)
            assert trajectory_actions[0].url == "https://console.notte.cc"

            assert isinstance(trajectory_actions[1], FillAction)
            assert trajectory_actions[1].id == "I1"
            assert trajectory_actions[1].value == "hello@notte.c"

            assert isinstance(trajectory_actions[2], ClickAction)
            assert trajectory_actions[2].id == "B1"

            assert isinstance(trajectory_actions[3], ScrollDownAction)

            assert isinstance(trajectory_actions[4], ScrapeAction)
            assert trajectory_actions[4].instructions == "scrape the company name"

            # Verify that the LLM was called the expected number of times
            assert mock_llm.call_count == 5


@pytest.mark.asyncio
@freeze_time("2025-01-15 12:00:00")
async def test_falco_agent_consistent_trajectory_with_completion():
    """Test that Falco agent completes successfully after the sequence"""

    # Define the sequence with a completion action at the end
    sequence = [
        # Step 1: goto: url=notte.cc
        create_agent_step_response(
            action=GotoAction(url="https://console.notte.cc"),
            page_summary="Navigating to notte.cc",
            next_goal="Navigate to the website",
        ),
        # Step 2: fill: "I1" hello@notte.c
        create_agent_step_response(
            action=FillAction(id="I1", value="hello@notte.c"),
            page_summary="On notte.cc homepage",
            previous_goal_status="success",
            previous_goal_eval="Successfully navigated to notte.cc",
            memory="Navigated to notte.cc",
            next_goal="Fill the email input field",
        ),
        # Step 3: click B1
        create_agent_step_response(
            action=ClickAction(id="B1"),
            page_summary="Email field filled",
            previous_goal_status="success",
            previous_goal_eval="Successfully filled email field",
            memory="Filled email field with hello@notte.c",
            next_goal="Click the submit button",
        ),
        # Step 4: scroll down
        create_agent_step_response(
            action=ScrollDownAction(amount=None),
            page_summary="Button clicked, page loaded",
            previous_goal_status="success",
            previous_goal_eval="Successfully clicked submit button",
            memory="Clicked submit button after filling email",
            next_goal="Scroll down to see more content",
        ),
        # Step 5: scrape with instruction "scrape the company name"
        create_agent_step_response(
            action=ScrapeAction(instructions="scrape the company name"),
            page_summary="Scrolled down, content visible",
            previous_goal_status="success",
            previous_goal_eval="Successfully scrolled down",
            memory="Scrolled down to view content",
            next_goal="Extract company name from the page",
        ),
        # Step 6: completion action
        create_agent_step_response(
            action=CompletionAction(
                success=True,
                answer="Successfully scraped company name: Notte",
            ),
            page_summary="Company name extracted",
            previous_goal_status="success",
            previous_goal_eval="Successfully scraped company name",
            memory="Completed the task successfully",
            next_goal="Task completed",
        ),
    ]

    # Create mock LLM engine
    mock_llm = MockLLMEngine(sequence)

    # Create mock validator
    mock_validator = MockValidator()

    # Use real browser session
    async with NotteSession(headless=True, enable_perception=False) as session:
        # Create Falco agent
        agent = FalcoAgent(
            window=session.window,
            max_steps=10,
        )
        task = "Test consistent trajectory with completion"
        # Patch the LLM engine and validator
        with (
            patch.object(agent, "llm", mock_llm),
            patch.object(agent, "validator", mock_validator),
            patch.object(agent.session._data_scraping_pipe.schema_pipe, "llmserve", MockLLMService),
        ):
            # Run the agent
            response = await agent.run(task=task)

            # Verify the response
            assert response is not None
            assert response.success is True
            assert "Successfully scraped company name: Notte" in response.answer

            # Verify the trajectory has the expected number of steps
            assert len(response.trajectory) == len(sequence) - 1, (
                f"Expected {len(sequence)} steps, got {len(response.trajectory)}. With last action: {response.trajectory[-1].action}"
            )

            # Verify the final action is a completion action
            final_action = response.trajectory[-1].action
            assert isinstance(final_action, ScrapeAction)
            assert final_action.instructions == "scrape the company name"
            assert "notte" in response.answer.lower()

            # Verify that the LLM was called the expected number of times
            assert mock_llm.call_count == 6

            # compare llm messages against the reference sequence
            messages = await agent.get_messages(task)
            with open(OUTPUT_MESSAGES_FILE, "w") as f:
                json.dump(messages, f)
            with open(MESSAGES_FILE, "r") as f:
                ref_messages: list[AllMessageValues] = json.load(f)
            assert len(messages) == len(ref_messages)
            for m, ref_m in zip(messages, ref_messages):
                assert m["role"] == ref_m["role"], f"Message role mismatch: {m['role']} != {ref_m['role']}"
                assert "content" in m, f"Message content missing: {m}"
                assert "content" in ref_m, f"Message content missing: {ref_m}"
                if isinstance(m["content"], str):
                    assert isinstance(ref_m["content"], str), (
                        f"Message content type mismatch: {type(m['content'])} != {type(ref_m['content'])}"
                    )
                    assert_strings_equal(m["content"], ref_m["content"], "Message content mismatch")
                elif isinstance(m["content"], list):
                    assert isinstance(ref_m["content"], list), (
                        f"Message content type mismatch: {type(m['content'])} != {type(ref_m['content'])}"
                    )
                    for c, ref_c in zip(m["content"], ref_m["content"]):
                        assert c["type"] == ref_c["type"], (
                            f"Message content type mismatch: {c['type']} != {ref_c['type']}"
                        )
                        if c["type"] == "text" and "text" in c and "text" in ref_c:
                            assert_strings_equal(c["text"], ref_c["text"], "Message content text mismatch")
                else:
                    raise ValueError(f"Unknown message content type: {type(m['content'])}")


@pytest.mark.asyncio
async def test_falco_agent_step_callback():
    """Test that step callback is called for each step"""

    callback_calls = []

    def step_callback(response: AgentStepResponse) -> None:
        callback_calls.append(response)

    # Define a simple sequence
    sequence = [
        create_agent_step_response(
            action=GotoAction(url="https://console.notte.cc"),
            page_summary="Navigating to notte.cc",
            next_goal="Navigate to the website",
        ),
        create_agent_step_response(
            action=FillAction(id="I1", value="hello@notte.c"),
            page_summary="On notte.cc homepage",
            next_goal="Fill the email input field",
        ),
    ]

    # Create mock LLM engine
    mock_llm = MockLLMEngine(sequence)

    # Create mock validator
    mock_validator = MockValidator()

    # Use real browser session
    async with NotteSession(headless=True, enable_perception=False) as session:
        # Create Falco agent with step callback
        agent = FalcoAgent(
            window=session.window,
            max_steps=10,
            step_callback=step_callback,
        )

        # Patch the LLM engine and validator
        with patch.object(agent, "llm", mock_llm), patch.object(agent, "validator", mock_validator):
            # Run the agent
            _ = await agent.run(task="Test step callback")

            # Verify the callback was called for each step + completion action
            assert len(callback_calls) == len(sequence) + 1

            # Verify the callback received the correct responses
            assert isinstance(callback_calls[0].action, GotoAction)
            assert callback_calls[0].action.url == "https://console.notte.cc"

            assert isinstance(callback_calls[1].action, FillAction)
            assert callback_calls[1].action.id == "I1"
            assert callback_calls[1].action.value == "hello@notte.c"
