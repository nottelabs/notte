from pathlib import Path

import chevron
from litellm import Message

from notte_core.errors.llm import InvalidPromptTemplateError


class PromptLibrary:
    def __init__(self, prompts_dir: str | Path) -> None:
        self.prompts_dir: Path = Path(prompts_dir)
        if not self.prompts_dir.exists():
            raise NotADirectoryError(f"Prompts directory not found: {prompts_dir}")

    def get(self, prompt_id: str) -> list[Message]:
        prompt_path: Path = self.prompts_dir / prompt_id
        prompt_files: list[Path] = list(prompt_path.glob("*.md"))
        if len(prompt_files) == 0:
            raise FileNotFoundError(f"Prompt template not found: {prompt_id}")
        messages: list[Message] = []
        for prompt_file in prompt_files:
            with open(prompt_file, "r") as file:
                content: str = file.read()
                role: str = prompt_file.name.split(".")[0]
                if role not in ["assistant", "user", "system", "tool", "function"]:
                    raise InvalidPromptTemplateError(
                        prompt_id=prompt_id,
                        message=(
                            f"invalid role: {role} in prompt template. "
                            "Valid roles are: assistant, user, system, tool, function"
                        ),
                    )
                messages.append(Message(role=role, content=content))  # type: ignore
        return messages

    def materialize(self, prompt_id: str, variables: dict[str, str] | None = None) -> list[dict[str, str]]:
        # TODO. You cant pass variables that are not in the prompt template
        # But you can fewer variables than in the prompt template
        _messages: list[Message] = self.get(prompt_id)
        messages: list[dict[str, str]] = []
        for message in _messages:
            if message.content is None:
                raise InvalidPromptTemplateError(
                    prompt_id=prompt_id,
                    message=f"Message content is none: {message.role}",
                )
            messages.append({"role": message.role, "content": message.content})

        if variables is None:
            return messages

        try:
            materialized_messages: list[dict[str, str]] = []
            for message in messages:
                formatted_content: str = chevron.render(message["content"], variables, warn=True)
                materialized_messages.append({"role": message["role"], "content": formatted_content})
            return materialized_messages
        except KeyError as e:
            raise InvalidPromptTemplateError(
                prompt_id=prompt_id,
                message=f"Missing required variable in prompt template: {str(e)}",
            ) from e
        except Exception as e:
            raise InvalidPromptTemplateError(
                prompt_id=prompt_id,
                message=f"Error formatting prompt: {str(e)}",
            ) from e
