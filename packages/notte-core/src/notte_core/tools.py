import json
from typing import Any, Generic, TypeVar, final

from litellm import AllMessageValues
from litellm.types.utils import ChatCompletionMessageToolCall  # pyright: ignore [reportMissingTypeStubs]
from loguru import logger
from pydantic import BaseModel

from notte_core.actions import BaseAction, BrowserAction, InteractionAction
from notte_core.agent_types import AgentCompletion, AgentState
from notte_core.llms.engine import LLMEngine

TResponseFormat = TypeVar("TResponseFormat", bound=BaseModel)


def action_to_litellm_tool(action_class: type[BaseAction]) -> dict[str, Any]:
    """Convert a Pydantic action class to LiteLLM tool format."""

    # Get the model schema
    action_schema = action_class.model_json_schema()
    state_schema = AgentState.model_json_schema()

    # Remove fields that shouldn't be exposed to the LLM
    non_agent_fields = action_class.non_agent_fields()
    if "properties" in action_schema:
        for field in non_agent_fields:
            action_schema["properties"].pop(field, None)

        # Update required fields to exclude non-agent fields
        if "required" in action_schema:
            action_schema["required"] = [f for f in action_schema["required"] if f not in non_agent_fields]

    combined_properties = {
        "state": state_schema,
        "action": action_schema,
    }
    combined_required = ["state", "action"]

    master_schema = {"type": "object", "properties": combined_properties, "required": combined_required}

    # Add $defs if present
    master_defs = {}
    if "$defs" in action_schema:
        master_defs.update(action_schema["$defs"])  # pyright: ignore [reportUnknownMemberType]
    if "$defs" in state_schema:
        master_defs.update(state_schema["$defs"])  # pyright: ignore [reportUnknownMemberType]

    if master_defs:
        master_schema["$defs"] = master_defs

    return {
        "type": "function",
        "function": {
            "name": action_class.name(),
            "description": f'Has two properties, one to log the "state" of the agent, and one with the {action_class.name()} "action" field: {action_class.model_fields.get("description", {}).default}',  # pyright: ignore [reportUnknownMemberType, reportAttributeAccessIssue]
            "parameters": master_schema,
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

    def validate_tool_call(self, tool_call: ChatCompletionMessageToolCall | str) -> AgentCompletion:
        """Validate tool call arguments and create the corresponding state/action instance."""
        if isinstance(tool_call, str):
            function_args = json.loads(tool_call)
            function_name = function_args["action"]["type"]
        else:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)

        # Find the action class
        action_class = self.all_actions.get(function_name)  # pyright: ignore [reportArgumentType]
        if not action_class:
            raise ValueError(f"Unknown action: {function_name}")

        if not ("state" in function_args.keys() and "action" in function_args.keys()):
            raise ValueError(f"Failed to validate {function_name}. Didn't include both 'state' and 'action'.")

        # Handle special cases for interaction actions
        if issubclass(action_class, InteractionAction):
            # Ensure id is provided for interaction actions
            if "id" not in function_args["action"]:
                raise ValueError(f"InteractionAction {function_name} requires 'id' field")

        # Create and validate the action
        try:
            state = AgentState.model_validate(function_args["state"])
            action = action_class.model_validate(function_args["action"])
            return AgentCompletion(state=state, action=action)
        except Exception as e:
            raise ValueError(f"Failed to validate {function_name} with args {function_args}: {e}")


class ToolLLMEngine(Generic[TResponseFormat]):
    system_prompt: str = """
CRITICAL: you must always return exactly one tool call.
CRITICAL: you must always use a tool call, never respond without using a tool call.
The tool call has two properties:
1. The first is to log the state, regardless of the current goal.
2. The second is the action which the tool corresponds to which best solves the current goal.
CRITICAL: each action must have a "type" sub property
"""

    def __init__(self, engine: LLMEngine):
        self.engine: LLMEngine = engine
        self.manager: ActionToolManager = ActionToolManager()

        self.tools: list[dict[str, Any]] = self.manager.get_tools()
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
    ) -> tuple[AgentCompletion, list[ChatCompletionMessageToolCall] | None]:
        response = await self.engine.completion(messages=self.patch_messages(messages), tools=self.tools)

        # Process tool calls
        tool_calls: list[ChatCompletionMessageToolCall] = response.choices[0].message.tool_calls  # pyright: ignore [reportUnknownMemberType,reportAttributeAccessIssue,reportAssignmentType]
        if tool_calls and len(tool_calls) > 1:
            raise ValueError("Too many tool calls found in response.")

        content: str | None = response.choices[0].message.content  # pyright: ignore [reportUnknownMemberType, reportAttributeAccessIssue, reportUnknownVariableType]

        if not tool_calls or len(tool_calls) == 0:
            # try fallback with normal response
            if not content or len(content) == 0:  # pyright: ignore[reportUnknownArgumentType]
                raise ValueError("No tool calls or response content")

            completion = self.manager.validate_tool_call(content)  # pyright: ignore[reportUnknownArgumentType]
        else:
            completion = self.manager.validate_tool_call(tool_calls[0])

        if content is not None and len(content) > 0 and not content.startswith("{"):  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
            logger.info(f"🧠 Tool thinking: {content}")
        return completion, tool_calls
