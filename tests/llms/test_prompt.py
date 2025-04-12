from pathlib import Path

import pytest
from notte_core.llms.prompt import PromptLibrary


@pytest.fixture
def temp_prompts_dir(tmp_path: Path) -> Path:
    # Create a temporary prompts directory structure
    prompt_dir = tmp_path / "test-prompt"
    prompt_dir.mkdir()

    # Create test prompt files
    user_file = prompt_dir / "user.md"
    system_file = prompt_dir / "system.md"
    assistant_file = prompt_dir / "assistant.md"

    _ = user_file.write_text("Hello {{name}}!")
    _ = system_file.write_text("System message")
    _ = assistant_file.write_text("Fixed response")

    return tmp_path


def test_prompt_library_initialization(temp_prompts_dir: Path) -> None:
    # Test successful initialization
    prompt_lib: PromptLibrary = PromptLibrary(temp_prompts_dir)
    assert prompt_lib.prompts_dir == temp_prompts_dir

    # Test initialization with non-existent directory
    with pytest.raises(NotADirectoryError):
        PromptLibrary("non/existent/path")


def test_get_prompt(temp_prompts_dir: Path) -> None:
    prompt_lib: PromptLibrary = PromptLibrary(temp_prompts_dir)

    # Test successful prompt retrieval
    messages = prompt_lib.get("test-prompt")
    assert len(messages) == 3
    assert any(msg.role == "user" for msg in messages)
    assert any(msg.role == "system" for msg in messages)
    assert any(msg.role == "assistant" for msg in messages)

    # Test non-existent prompt
    with pytest.raises(FileNotFoundError):
        prompt_lib.get("non-existent-prompt")


def test_materialize_prompt(temp_prompts_dir: Path) -> None:
    prompt_lib: PromptLibrary = PromptLibrary(temp_prompts_dir)

    # Test successful materialization with variables
    variables = {"name": "John"}
    messages = prompt_lib.materialize("test-prompt", variables)

    assert len(messages) == 3
    user_message = next(msg for msg in messages if msg["role"] == "user")
    assert user_message["content"] == "Hello John!"

    # Test materialization without variables
    messages = prompt_lib.materialize("test-prompt")
    assert len(messages) == 3

    # Test materialization with missing variable
    # TODO: Andrea check this
    # with pytest.raises(ValueError, match="Missing required variable"):
    #     prompt_lib.materialize("test-prompt", {"wrong_var": "value"})
