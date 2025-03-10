from pydantic import BaseModel, Field


# Mock classes to avoid circular imports
class NudgeHint(BaseModel):
    """A hint or nudge to help the agent get back on track."""

    message: str = Field(..., description="The hint message to provide to the agent")
    reason: str = Field(..., description="The reason why this hint is being provided")
    severity: str = Field(..., description="The severity of the issue (low, medium, high)")


class NudgeAnalysisResult(BaseModel):
    """The result of analyzing the agent's trajectory."""

    needs_nudge: bool = Field(..., description="Whether the agent needs a nudge")
    hints: list[NudgeHint] = Field(default_factory=list, description="List of hints to provide to the agent")

    def get_formatted_hints(self) -> str:
        """Format the hints as a string to be included in the agent's prompt."""
        if not self.needs_nudge or not self.hints:
            return ""

        result = "🚨 **Agent Nudge**:\n\n"
        for hint in self.hints:
            result += f"- {hint.message}\n"
        return result


class MockAction:
    def __init__(self, name: str, message: str = ""):
        self.action_name = name
        self.action_message = message
        self.id = f"mock-{name}"

    def name(self) -> str:
        return self.action_name

    def execution_message(self) -> str:
        return self.action_message

    def dump_str(self) -> str:
        return f"{self.action_name}({self.action_message})"


class MockAgentState:
    def __init__(self, previous_goal_status="unknown", previous_goal_eval="", page_summary="", next_goal="", memory=""):
        self.previous_goal_status = previous_goal_status
        self.previous_goal_eval = previous_goal_eval
        self.page_summary = page_summary
        self.next_goal = next_goal
        self.memory = memory
        self.relevant_interactions = []


class MockStepAgentOutput:
    def __init__(self, state, actions=None):
        self.state = state
        self.actions = actions or []

    def model_dump_json(self, **kwargs):
        return "{}"


class MockTrajectoryStep:
    def __init__(self, agent_response, results=None):
        self.agent_response = agent_response
        self.results = results or []


class MockTrajectoryHistory:
    def __init__(self, max_error_length=None):
        self.steps = []
        self.max_error_length = max_error_length

    def reset(self):
        self.steps = []

    def add_output(self, output):
        self.steps.append(MockTrajectoryStep(agent_response=output, results=[]))

    def add_step(self, step):
        if len(self.steps) == 0:
            raise ValueError("Cannot add step to empty trajectory. Use `add_output` first.")
        else:
            self.steps[-1].results.append(step)


class MockNudgePipe:
    def __init__(self):
        pass

    def forward(self, trajectory, **params):
        # For testing, we'll just return a predefined result
        if not trajectory.steps:
            return NudgeAnalysisResult(needs_nudge=False)

        # Check if we should return a nudge
        return self._mock_result

    def set_mock_result(self, result):
        self._mock_result = result


class MockFalcoAgentConfig:
    def __init__(
        self, enable_nudges=True, nudge_max_steps_to_analyze=3, nudge_failure_threshold=3, nudge_max_tokens=1000
    ):
        self.enable_nudges = enable_nudges
        self.nudge_max_steps_to_analyze = nudge_max_steps_to_analyze
        self.nudge_failure_threshold = nudge_failure_threshold
        self.nudge_max_tokens = nudge_max_tokens


class MockConversation:
    def __init__(self):
        self.messages_list = []
        self.user_messages = []
        self.system_messages = []
        self.assistant_messages = []

    def reset(self):
        self.messages_list = []
        self.user_messages = []
        self.system_messages = []
        self.assistant_messages = []

    def add_user_message(self, content):
        self.user_messages.append(content)

    def add_system_message(self, content):
        self.system_messages.append(content)

    def add_assistant_message(self, content):
        self.assistant_messages.append(content)

    def messages(self):
        return self.messages_list


class MockFalcoAgent:
    def __init__(self, config=None):
        self.config = config or MockFalcoAgentConfig()
        self.trajectory = MockTrajectoryHistory()
        self.conv = MockConversation()
        self.nudge_pipe = MockNudgePipe() if self.config.enable_nudges else None
        self.last_nudge_result = None

    def get_messages(self, task):
        self.conv.reset()

        # Check if nudges are needed
        nudge_msg = ""
        if self.config.enable_nudges and self.nudge_pipe is not None and len(self.trajectory.steps) > 0:
            # Analyze the trajectory and get nudges if needed
            self.last_nudge_result = self.nudge_pipe.forward(
                self.trajectory,
                max_steps_to_analyze=self.config.nudge_max_steps_to_analyze,
                failure_threshold=self.config.nudge_failure_threshold,
                max_tokens=self.config.nudge_max_tokens,
            )

            # If nudges are needed, add them to the message
            if self.last_nudge_result.needs_nudge:
                nudge_msg = self.last_nudge_result.get_formatted_hints()
                if nudge_msg:
                    self.conv.add_user_message(content=nudge_msg)

        return self.conv.messages()


class TestFalcoAgentNudgeIntegration:
    def test_nudge_pipe_initialization(self):
        """Test that the nudge pipe is initialized when enabled."""
        config = MockFalcoAgentConfig(enable_nudges=True)
        agent = MockFalcoAgent(config=config)

        assert agent.nudge_pipe is not None

    def test_nudge_pipe_not_initialized_when_disabled(self):
        """Test that the nudge pipe is not initialized when disabled."""
        config = MockFalcoAgentConfig(enable_nudges=False)
        agent = MockFalcoAgent(config=config)

        assert agent.nudge_pipe is None

    def test_get_messages_with_nudge(self):
        """Test that nudges are added to messages when needed."""
        agent = MockFalcoAgent()

        # Setup mock trajectory with some steps
        agent_response = MockStepAgentOutput(
            state=MockAgentState(page_summary="Google homepage", next_goal="Search for cats")
        )
        agent.trajectory.add_output(agent_response)

        # Setup mock nudge result
        mock_hint = NudgeHint(message="Try a different approach", reason="You seem stuck", severity="medium")
        mock_result = NudgeAnalysisResult(needs_nudge=True, hints=[mock_hint])
        agent.nudge_pipe.set_mock_result(mock_result)

        # Call get_messages
        agent.get_messages("Search for cats")

        # Verify nudge message was added to conversation
        assert any("Try a different approach" in msg for msg in agent.conv.user_messages)

    def test_get_messages_without_nudge(self):
        """Test that no nudge is added when not needed."""
        agent = MockFalcoAgent()

        # Setup mock trajectory with some steps
        agent_response = MockStepAgentOutput(
            state=MockAgentState(page_summary="Google homepage", next_goal="Search for cats")
        )
        agent.trajectory.add_output(agent_response)

        # Setup mock nudge result with no nudge needed
        mock_result = NudgeAnalysisResult(needs_nudge=False, hints=[])
        agent.nudge_pipe.set_mock_result(mock_result)

        # Call get_messages
        agent.get_messages("Search for cats")

        # Verify no nudge message was added
        assert not any("Agent Nudge" in msg for msg in agent.conv.user_messages)

        # Verify the last_nudge_result was set
        assert agent.last_nudge_result == mock_result
        assert not agent.last_nudge_result.needs_nudge

    def test_get_messages_no_steps(self):
        """Test that nudge pipe is not called when there are no steps."""
        agent = MockFalcoAgent()

        # Setup empty trajectory
        agent.trajectory = MockTrajectoryHistory()

        # Call get_messages
        agent.get_messages("Search for cats")

        # Verify no nudge message was added
        assert not any("Agent Nudge" in msg for msg in agent.conv.user_messages)

        # Verify the last_nudge_result was not set
        assert agent.last_nudge_result is None

    def test_get_messages_nudge_disabled(self):
        """Test that nudge pipe is not called when nudges are disabled."""
        config = MockFalcoAgentConfig(enable_nudges=False)
        agent = MockFalcoAgent(config=config)

        # Setup mock trajectory with some steps
        agent_response = MockStepAgentOutput(
            state=MockAgentState(page_summary="Google homepage", next_goal="Search for cats")
        )
        agent.trajectory.add_output(agent_response)

        # Call get_messages
        agent.get_messages("Search for cats")

        # Verify no nudge message was added
        assert not any("Agent Nudge" in msg for msg in agent.conv.user_messages)

        # Verify the nudge_pipe is None
        assert agent.nudge_pipe is None
