from enum import Enum
from typing import Self

import regex as re
from loguru import logger
from notte_core.actions.percieved import ActionParameter
from notte_core.common.config import FrozenConfig
from notte_core.errors.llm import LLMParsingError
from notte_core.errors.processing import InvalidInternalCheckError

from notte_browser.tagging.types import PossibleAction


class ActionListingParserType(Enum):
    MARKDOWN = "markdown"
    TABLE = "table"
    JSON = "json"  # TODO


class ActionListingParserConfig(FrozenConfig):
    type: ActionListingParserType = ActionListingParserType.TABLE
    allow_partial: bool = True

    def set_markdown(self: Self) -> Self:
        return self._copy_and_validate(type=ActionListingParserType.MARKDOWN)

    def set_table(self: Self) -> Self:
        return self._copy_and_validate(type=ActionListingParserType.TABLE)

    def set_json(self: Self) -> Self:
        return self._copy_and_validate(type=ActionListingParserType.JSON)


class ActionListingParserPipe:
    @staticmethod
    def forward(content: str, config: ActionListingParserConfig) -> list[PossibleAction]:
        # partial is enabled by default to avoid too many retries.
        match config.type:
            case ActionListingParserType.MARKDOWN:
                return parse_markdown_action_list(content, partial=config.allow_partial)
            case ActionListingParserType.TABLE:
                return parse_table(content, partial=config.allow_partial)
            case _:
                raise InvalidInternalCheckError(
                    check=(
                        f"invalid action listing parser: {config.type}. "
                        f"Valid parsers are: {list(ActionListingParserType)}."
                    ),
                    url="unknown url",
                    dev_advice=(
                        "If this error is raised, it probably means that you forgot to add a new entry in "
                        "`ActionListingParser.parse`."
                    ),
                )


def parse_action_ids(action: str) -> list[str]:
    """

    Should be able to parse action ids in the following format:
    - B1 or [B1]
    - B1-3 or [B1-3]
    - B1-B3 or [B1-B3]
    - B1, B2, B3 or [B1, B2, B3]
    """
    if ":" not in action:
        raise LLMParsingError(f"Action line '{action}' should contain ':'")

    id_part = action.split(":")[0].replace("[", "").replace("]", "").replace("ID ", "").strip()
    if "," in id_part:
        return [id.strip() for id in id_part.split(",")]
    if "-" not in id_part:
        return [id_part]

    range_id_parts = id_part.split("-")
    if len(range_id_parts) != 2:
        raise LLMParsingError(f"Invalid action id group: {action}")

    def split_id(sub_id_part: str) -> tuple[str, int]:
        if sub_id_part[0].isalpha():
            return sub_id_part[0], int(sub_id_part[1:])
        return "", int(sub_id_part)

    first_letter, range_start = split_id(range_id_parts[0].strip())
    other_letter, range_end = split_id(range_id_parts[1].strip())

    if len(first_letter) <= 0 or not first_letter.isalpha():
        raise LLMParsingError(f"Not a valid first letter: '{first_letter}' for '{id_part}' and range {range_id_parts}")
    if (len(other_letter) > 0) and first_letter != other_letter:
        raise LLMParsingError(f"Letters are not the same: {first_letter} and {other_letter} for '{id_part}'")

    return [f"{first_letter}{id}" for id in range(range_start, range_end + 1)]


def parse_action_parameters(action: str) -> list[ActionParameter]:
    """
    Should be able to parse action parameters in the following format:
    - (parameterName1: Type1 = [value1, value2, ..., valueN],
            parameterName2: Type2 = [value1, value2, ..., valueM])
    """

    def parse_name_and_type(parameter_str: str) -> tuple[str, str]:
        if ":" not in parameter_str:
            raise LLMParsingError(f"Invalid parameter: {parameter_str} (should be in the format parameterName: Type)")
        parts = parameter_str.split(":")
        if len(parts) != 2:
            raise LLMParsingError(f"Invalid parameter: {parameter_str} (should be in the format parameterName: Type)")
        return parts[0].strip(), parts[1].strip()

    def parse_values(values_str: str) -> list[str]:
        match = re.search(r"\[(.*)\]", values_str, re.DOTALL)
        if not match:
            raise LLMParsingError(
                f"Invalid values: {values_str} (should be in the format [value1, value2, ..., valueN])"
            )
        return [value.strip() for value in match.group(1).split(",")]

    def split_parameters(parameters_str: str) -> list[str]:
        output: list[str] = []
        splits: list[str] = parameters_str.split(",")
        current: list[str] = []
        is_in_brackets = False
        for split in splits:
            if "[" in split:
                is_in_brackets = True

            if not is_in_brackets:
                output.append(split)
            else:
                current.append(split)

            if "]" in split:
                is_in_brackets = False
                output.append(",".join(current))
                current = []

        return output

    parameters: list[ActionParameter] = []
    matches: list[str] = re.findall(r"\(([^)]+)\)", action)
    if matches and ":" in matches[-1]:
        parameters_str = matches[-1]
        for parameter_str in split_parameters(parameters_str):
            # parse each parameter
            parameter_list_str = parameter_str.strip().split("=")
            if len(parameter_list_str) > 2:
                raise LLMParsingError(f"Invalid parameter: {parameter_str} (should not contain more than one '=')")
            name, type_str = parse_name_and_type(parameter_list_str[0])
            values = []
            if len(parameter_list_str) == 2:
                values = parse_values(parameter_list_str[1])
            # add parameter to list
            parameters.append(
                ActionParameter(
                    name=name,
                    type=type_str,
                    values=values,
                    default=None,
                )
            )
    return parameters


def parse_markdown_action_list(
    markdown_content: str,
    parse_parameters: bool = True,
    partial: bool = False,
) -> list[PossibleAction]:
    actions: list[PossibleAction] = []
    current_category: str | None = None

    # Process each line
    for line in markdown_content.split("\n"):
        try:
            line = line.strip()
            if not line:
                continue

            if any(
                disabled in line.lower()
                for disabled in [
                    "text-related action",
                    "hover action",
                    "keyboard navigation action",
                    "* none",
                ]
            ):
                logger.warning(f"Excluding {line} because it's a disabled action")
                continue

            # Check if it's a category header (starts with #)
            if line.startswith("#"):
                current_category = line.lstrip("#").strip()
            # Check if it's a bullet point
            elif line.startswith("*"):
                bullet_text = line.lstrip("*").strip()
                action_id = parse_action_ids(bullet_text)
                parameters = parse_action_parameters(bullet_text) if parse_parameters else []
                action_description = bullet_text.split(":")[1].strip()
                if len(parameters) > 0:
                    action_description = action_description.split("(")[0].strip()
                if current_category is None:
                    raise LLMParsingError("Category is required for each action but is currently None.")
                actions.append(
                    PossibleAction(
                        id=action_id[0],
                        description=action_description,
                        category=current_category,
                        params=parameters,
                    )
                )
            else:
                if partial:
                    logger.warning(f"[Markdown parsing] Failed to parse action line: {line}")
                    continue
                raise LLMParsingError(f"Invalid action line: {line}. Action lines should start with '*' or '#'")
        except Exception as e:
            if partial:
                logger.warning(f"[Markdown parsing] Failed to parse action line: {line} with error: {e}")
                continue
            raise e
    return actions


def parse_table_parameter(param_string: str) -> ActionParameter:
    """
    Parse a parameter string into an ActionParameter object.

    Args:
            param_string: String in format 'name: value type: value [default=value] [values=[v1,v2,...]]'

    Returns:
            ActionParameter object

    Raises:
            ValueError: If required fields are missing or format is invalid
    """
    # Initialize parameter attributes
    name: str | None = None
    param_type: str | None = None
    default: str | None = None
    values: list[str] = []

    # Split the string into main parts based on commas, but preserve commas inside brackets
    parts: list[str] = []
    current_part: list[str] = []
    bracket_count: int = 0

    for char in param_string:
        if char == "[":
            bracket_count += 1
        elif char == "]":
            bracket_count -= 1
        elif char == "," and bracket_count == 0:
            parts.append("".join(current_part).strip())
            current_part = []
            continue
        current_part.append(char)

    if current_part:
        parts.append("".join(current_part).strip())

    # Parse each part
    for part in parts:
        if ":" in part:
            key_values = [kv.strip() for kv in part.split(":")]
            for i in range(0, len(key_values) - 1, 2):
                key = key_values[i].strip()
                value = key_values[i + 1].strip()

                if key == "name":
                    name = value
                elif key == "type":
                    param_type = value

        elif "=" in part:
            key, value = [x.strip() for x in part.split("=", 1)]

            if key == "default":
                # Remove quotes if present
                default = value.strip("\"'")

            elif key == "values":
                # Extract list values, handling the bracket format
                match = re.match(r"\[(.*)\]", value)
                if match:
                    values_str = match.group(1)
                    values = [v.strip().strip("\"'") for v in values_str.split(",")]
                else:
                    raise LLMParsingError(
                        f"Action parameter values must be in list format: [value1, value2, ...] but is: '{value}'"
                    )

    # Validate required fields
    if not name or not param_type:
        raise LLMParsingError(f"Name and type are required fields but not found in : {param_string}")

    return ActionParameter(name=name, type=param_type, default=default, values=values)


def parse_table(table_text: str, partial: bool = False) -> list[PossibleAction]:
    """
    Parse a table of actions into a list of PossibleAction objects.

    Args:
            table_text: The text of the table to parse.
            partial: Whether to fail if the table is not complete or return a partial list of actions.

    Returns:
            A list of PossibleAction objects.
    """
    # Skip empty lines
    lines = [line.strip() for line in table_text.split("\n") if line.strip()]
    lines = [line for line in lines if not line.startswith("|---") and "|" in line]

    if not lines:
        raise LLMParsingError("Empty table returned by LLM. At least one action should be returned.")

    # Validate headers
    expected_headers = ["ID", "Description", "Parameters", "Category"]
    headers = [col.strip() for col in lines[0].split("|")[1:-1]]

    if headers != expected_headers:
        raise LLMParsingError(f"Invalid table headers. Expected {expected_headers}, got {headers}")

    actions: list[PossibleAction] = []

    for line in lines[1:]:  # Skip header row
        try:
            # Split the line into columns and clean whitespace
            cols = [col.strip() for col in line.split("|")[1:-1]]
            if len(cols) != 4:
                continue

            id_, description, params_str, category = cols

            action = PossibleAction(
                id=id_,
                description=description,
                category=category,
                params=[] if params_str == "" else [parse_table_parameter(params_str)],
            )
            actions.append(action)
        except Exception as e:
            if partial:
                logger.warning(f"[Markdown table parsing] Failed to parse action line: {line} with error: {e}")
                continue
            raise e

    return actions
