import json
from typing import Any, Generic, TypeVar, final

from litellm import AllMessageValues
from litellm.types.utils import ChatCompletionMessageToolCall  # pyright: ignore [reportMissingTypeStubs]
from loguru import logger
from pydantic import BaseModel

from notte_core.actions import ActionUnion, BaseAction, BrowserAction, InteractionAction
from notte_core.llms.engine import LLMEngine

TResponseFormat = TypeVar("TResponseFormat", bound=BaseModel)


def action_to_litellm_tool(action_class: type[BaseAction]) -> dict[str, Any]:
    """Convert a Pydantic action class to LiteLLM tool format."""

    # Get the model schema
    schema = action_class.model_json_schema()

    # Remove fields that shouldn't be exposed to the LLM
    non_agent_fields = action_class.non_agent_fields()
    if "properties" in schema:
        for field in non_agent_fields:
            schema["properties"].pop(field, None)

        # Update required fields to exclude non-agent fields
        if "required" in schema:
            schema["required"] = [f for f in schema["required"] if f not in non_agent_fields]

    return {
        "type": "function",
        "function": {
            "name": action_class.name(),
            "description": action_class.model_fields.get("description", {}).default,  # pyright: ignore [reportUnknownMemberType, reportAttributeAccessIssue]
            "parameters": schema,
        },
    }


def create_all_tools() -> list[dict[str, Any]]:
    """Create tools for all registered actions."""
    tools: list[dict[str, Any]] = []

    # Add browser actions
    for action_class in BrowserAction.BROWSER_ACTION_REGISTRY.values():
        tools.append(action_to_litellm_tool(action_class))

    # Add interaction actions
    for action_class in InteractionAction.INTERACTION_ACTION_REGISTRY.values():
        tools.append(action_to_litellm_tool(action_class))

    return tools


def create_browser_tools_only() -> list[dict[str, Any]]:
    """Create tools only for browser actions."""
    return [action_to_litellm_tool(action_class) for action_class in BrowserAction.BROWSER_ACTION_REGISTRY.values()]


def create_interaction_tools_only() -> list[dict[str, Any]]:
    """Create tools only for interaction actions."""
    return [
        action_to_litellm_tool(action_class) for action_class in InteractionAction.INTERACTION_ACTION_REGISTRY.values()
    ]


@final
class ActionToolManager:
    """Manager class to handle action tool creation and execution validation."""

    def __init__(self):
        self.browser_actions = BrowserAction.BROWSER_ACTION_REGISTRY
        self.interaction_actions = InteractionAction.INTERACTION_ACTION_REGISTRY
        self.all_actions = {**self.browser_actions, **self.interaction_actions}

    def get_tools(self, include_browser: bool = True, include_interaction: bool = True) -> list[dict[str, Any]]:
        """Get tools based on what action types to include."""
        tools: list[dict[str, Any]] = []

        if include_browser:
            tools.extend(create_browser_tools_only())

        if include_interaction:
            tools.extend(create_interaction_tools_only())

        return tools

    def validate_and_create_action(self, tool_call: ChatCompletionMessageToolCall) -> BaseAction:
        """Validate tool call arguments and create the corresponding action instance."""
        function_name = tool_call.function.name
        function_args = json.loads(tool_call.function.arguments)

        # Find the action class
        action_class = self.all_actions.get(function_name)  # pyright: ignore [reportArgumentType]
        if not action_class:
            raise ValueError(f"Unknown action: {function_name}")

        # Handle special cases for interaction actions
        if issubclass(action_class, InteractionAction):
            # Ensure id is provided for interaction actions
            if "id" not in function_args:
                raise ValueError(f"InteractionAction {function_name} requires 'id' field")

        # Create and validate the action
        try:
            action = action_class.model_validate(function_args)
            return action
        except Exception as e:
            raise ValueError(f"Failed to validate {function_name} with args {function_args}: {e}")


class ToolLLMEngine(Generic[TResponseFormat]):
    system_prompt: str = """
CRITICAL: you must always return exactly two tool calls:
1. The first tool call should always be 'log_state', regardless of the current goal.
2. The second tool call should be one of the action tools that best solves the current goal. You should always call the 'log_state' tool first.
"""

    def __init__(self, engine: LLMEngine, state_response_format: type[TResponseFormat]):
        self.engine: LLMEngine = engine
        self.state_response_format: type[TResponseFormat] = state_response_format
        self.manager: ActionToolManager = ActionToolManager()

        # Helper function for quick tool creation
        log_state_tool = {
            "type": "function",
            "function": {
                "name": "log_state",
                "description": "Log the state of the agent. You MUST call this tool first before calling any other tool.",
                "parameters": self.state_response_format.model_json_schema(),
            },
        }
        self.tools: list[dict[str, Any]] = [log_state_tool] + self.manager.get_tools()
        logger.info(f"🔧 Created {len(self.tools)} tools")

    def patch_messages(self, messages: list[AllMessageValues]) -> list[AllMessageValues]:
        if len(messages) == 0:
            messages.append({"role": "system", "content": self.system_prompt})
        elif messages[0]["role"] == "system":
            messages[0]["content"] += self.system_prompt
        else:
            messages.insert(0, {"role": "system", "content": self.system_prompt})
        return messages

    async def tool_completion(
        self, messages: list[AllMessageValues]
    ) -> tuple[TResponseFormat, ActionUnion, list[ChatCompletionMessageToolCall]]:
        response = await self.engine.completion(
            messages=self.patch_messages(messages), tools=self.tools, response_format=self.state_response_format
        )

        # Process tool calls
        tool_calls: list[ChatCompletionMessageToolCall] = response.choices[0].message.tool_calls  # pyright: ignore [reportUnknownMemberType,reportAttributeAccessIssue,reportAssignmentType]
        if not tool_calls or len(tool_calls) == 0:
            raise ValueError("No tool calls found in response")

        # first tool call should be log_state
        if tool_calls[0].function.name != "log_state":
            raise ValueError("First tool call should be log_state")
        state = self.state_response_format.model_validate_json(tool_calls[0].function.arguments)
        if len(tool_calls) == 1:
            raise ValueError(
                "No action tool calls found in response. You should always select 2 tools (1 for log_state and 1 for the action)."
            )

        if len(tool_calls) > 2:
            raise ValueError(
                "Too many tool calls found in response. You should always select 2 tools (1 for log_state and 1 for the action)."
            )

        action = self.manager.validate_and_create_action(tool_calls[1])
        content: str | None = response.choices[0].message.content  # pyright: ignore [reportUnknownMemberType,reportAttributeAccessIssue, reportUnknownVariableType]
        if content is not None and len(content) > 0:  # pyright: ignore[reportUnknownArgumentType]
            logger.info(f"🧠 Tool thinking: {content}")
        return state, action, tool_calls
