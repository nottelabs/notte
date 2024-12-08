from pathlib import Path
from typing import Any

import chevron
from litellm import Message


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
                messages.append(Message(role=role, content=content))
        return messages

    def materialize(self, prompt_id: str, variables: dict[str, Any] | None = None) -> list[dict[str, str | None]]:
        # TODO. You cant pass variables that are not in the prompt template
        # But you can fewer variables than in the prompt template
        messages = self.get(prompt_id)
        if variables is None:
            return messages

        try:
            materialized_messages: list[Message] = []
            for message in messages:
                formatted_content: str = chevron.render(message.content, variables)
                materialized_messages.append(Message(role=message.role, content=formatted_content))
            return self.dictify(materialized_messages)
        except KeyError as e:
            raise ValueError(f"Missing required variable in prompt template: {str(e)}")
        except Exception as e:
            raise ValueError(f"Error formatting prompt: {str(e)}")

    def dictify(self, messages: list[Message]) -> list[dict[str, str | None]]:
        return [
            {
                "role": message.role,
                "content": message.content,
            }
            for message in messages
        ]
