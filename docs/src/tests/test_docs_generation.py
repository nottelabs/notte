import re

import pytest

from .test_snippets import SDK_DIR


def extract_param_fields(content: str) -> list[str]:
    """
    Extract ParamField blocks from MDX content and normalize them for comparison.
    Returns a list of normalized parameter field strings.
    """
    # Find all ParamField blocks
    param_pattern = r'<ParamField[^>]*path="([^"]*)"[^>]*type="([^"]*)"[^>]*>(.*?)</ParamField>'
    matches = re.findall(param_pattern, content, re.DOTALL | re.MULTILINE)

    normalized_params = []
    for path, type_str, description in matches:
        # Normalize the description by stripping whitespace and removing extra spaces
        desc_clean = re.sub(r"\s+", " ", description.strip())
        normalized_params.append(f"{path}|{type_str}|{desc_clean}")

    return sorted(normalized_params)


def test_agent_parameters_in_sync():
    """
    Test that parameters in sdk/manual/agent.mdx are synchronized with
    the source parameters in sdk/remoteagentfactory/__call__.mdx
    """
    agent_file = SDK_DIR / "manual" / "agent.mdx"
    factory_file = SDK_DIR / "remoteagent" / "__init__.mdx"

    assert agent_file.exists(), f"Agent file not found: {agent_file}"
    assert factory_file.exists(), f"Factory file not found: {factory_file}"

    agent_content = agent_file.read_text("utf-8")
    factory_content = factory_file.read_text("utf-8")

    # Extract parameter sections from both files
    agent_params = extract_param_fields(agent_content)
    factory_params = extract_param_fields(factory_content)

    # Compare the normalized parameter lists
    missing_in_agent = set(factory_params) - set(agent_params)
    extra_in_agent = set(agent_params) - set(factory_params)

    error_messages = []
    if missing_in_agent:
        error_messages.append(f"Parameters missing in agent.mdx: {missing_in_agent}")
    if extra_in_agent:
        error_messages.append(f"Extra parameters in agent.mdx: {extra_in_agent}")

    if error_messages:
        pytest.fail(
            f"Parameter synchronization failed between {agent_file} and {factory_file}:\n" + "\n".join(error_messages)
        )


def test_session_parameters_in_sync():
    """
    Test that parameters in sdk/manual/session.mdx are synchronized with
    the source parameters in sdk/remotesession/__init__.mdx
    """
    session_file = SDK_DIR / "manual" / "session.mdx"
    factory_file = SDK_DIR / "remotesession" / "__init__.mdx"

    assert session_file.exists(), f"Session file not found: {session_file}"
    assert factory_file.exists(), f"Factory file not found: {factory_file}"

    session_content = session_file.read_text("utf-8")
    factory_content = factory_file.read_text("utf-8")

    # Extract parameter sections from both files
    session_params = extract_param_fields(session_content)
    factory_params = extract_param_fields(factory_content)

    # Compare the normalized parameter lists
    missing_in_session = set(factory_params) - set(session_params)
    extra_in_session = set(session_params) - set(factory_params)

    error_messages = []
    if missing_in_session:
        error_messages.append(f"Parameters missing in session.mdx: {missing_in_session}")
    if extra_in_session:
        error_messages.append(f"Extra parameters in session.mdx: {extra_in_session}")

    if error_messages:
        pytest.fail(
            f"Parameter synchronization failed between {session_file} and {factory_file}:\n" + "\n".join(error_messages)
        )


def test_workflow_parameters_in_sync():
    """
    Test that parameters in sdk/manual/workflow.mdx are synchronized with
    the source parameters in sdk/remoteworkflowfactory/__init__.mdx
    """
    workflow_file = SDK_DIR / "manual" / "workflow.mdx"
    factory_file = SDK_DIR / "remoteworkflow" / "__init__.mdx"

    assert workflow_file.exists(), f"Workflow file not found: {workflow_file}"
    assert factory_file.exists(), f"Factory file not found: {factory_file}"

    workflow_content = workflow_file.read_text("utf-8")
    factory_content = factory_file.read_text("utf-8")

    # Extract parameter sections from both files
    workflow_params = extract_param_fields(workflow_content)
    factory_params = extract_param_fields(factory_content)

    # Compare the normalized parameter lists
    missing_in_workflow = set(factory_params) - set(workflow_params)
    extra_in_workflow = set(workflow_params) - set(factory_params)

    error_messages = []
    if missing_in_workflow:
        error_messages.append(f"Parameters missing in workflow.mdx: {missing_in_workflow}")
    if extra_in_workflow:
        error_messages.append(f"Extra parameters in workflow.mdx: {extra_in_workflow}")

    if error_messages:
        pytest.fail(
            f"Parameter synchronization failed between {workflow_file} and {factory_file}:\n"
            + "\n".join(error_messages)
        )


def test_vault_parameters_in_sync():
    """
    Test that parameters in sdk/manual/vault.mdx are synchronized with
    the source parameters in sdk/nottevault/__init__.mdx
    """
    vault_file = SDK_DIR / "manual" / "vault.mdx"
    factory_file = SDK_DIR / "nottevault" / "__init__.mdx"

    assert vault_file.exists(), f"Vault file not found: {vault_file}"
    assert factory_file.exists(), f"Factory file not found: {factory_file}"

    vault_content = vault_file.read_text("utf-8")
    factory_content = factory_file.read_text("utf-8")

    # Extract parameter sections from both files
    vault_params = extract_param_fields(vault_content)
    factory_params = extract_param_fields(factory_content)

    # Compare the normalized parameter lists
    missing_in_vault = set(factory_params) - set(vault_params)
    extra_in_vault = set(vault_params) - set(factory_params)

    error_messages = []
    if missing_in_vault:
        error_messages.append(f"Parameters missing in vault.mdx: {missing_in_vault}")
    if extra_in_vault:
        error_messages.append(f"Extra parameters in vault.mdx: {extra_in_vault}")

    if error_messages:
        pytest.fail(
            f"Parameter synchronization failed between {vault_file} and {factory_file}:\n" + "\n".join(error_messages)
        )


def test_persona_parameters_in_sync():
    """
    Test that parameters in sdk/manual/persona.mdx are synchronized with
    the source parameters in sdk/nottepersona/__init__.mdx
    """
    persona_file = SDK_DIR / "manual" / "persona.mdx"
    factory_file = SDK_DIR / "nottepersona" / "__init__.mdx"

    assert persona_file.exists(), f"Persona file not found: {persona_file}"
    assert factory_file.exists(), f"Factory file not found: {factory_file}"

    persona_content = persona_file.read_text("utf-8")
    factory_content = factory_file.read_text("utf-8")

    # Extract parameter sections from both files
    persona_params = extract_param_fields(persona_content)
    factory_params = extract_param_fields(factory_content)

    # Compare the normalized parameter lists
    missing_in_persona = set(factory_params) - set(persona_params)
    extra_in_persona = set(persona_params) - set(factory_params)

    error_messages = []
    if missing_in_persona:
        error_messages.append(f"Parameters missing in persona.mdx: {missing_in_persona}")
    if extra_in_persona:
        error_messages.append(f"Extra parameters in persona.mdx: {extra_in_persona}")

    if error_messages:
        pytest.fail(
            f"Parameter synchronization failed between {persona_file} and {factory_file}:\n" + "\n".join(error_messages)
        )


def test_file_storage_parameters_in_sync():
    """
    Test that parameters in sdk/manual/file_storage.mdx are synchronized with
    the source parameters in sdk/remotefilestorage/__init__.mdx
    """
    file_storage_file = SDK_DIR / "manual" / "file_storage.mdx"
    factory_file = SDK_DIR / "remotefilestorage" / "__init__.mdx"

    assert file_storage_file.exists(), f"File storage file not found: {file_storage_file}"
    assert factory_file.exists(), f"Factory file not found: {factory_file}"

    file_storage_content = file_storage_file.read_text("utf-8")
    factory_content = factory_file.read_text("utf-8")

    # Extract parameter sections from both files
    file_storage_params = extract_param_fields(file_storage_content)
    factory_params = extract_param_fields(factory_content)

    # Compare the normalized parameter lists
    missing_in_file_storage = set(factory_params) - set(file_storage_params)
    extra_in_file_storage = set(file_storage_params) - set(factory_params)

    error_messages = []
    if missing_in_file_storage:
        error_messages.append(f"Parameters missing in file_storage.mdx: {missing_in_file_storage}")
    if extra_in_file_storage:
        error_messages.append(f"Extra parameters in file_storage.mdx: {extra_in_file_storage}")

    if error_messages:
        pytest.fail(
            f"Parameter synchronization failed between {file_storage_file} and {factory_file}:\n"
            + "\n".join(error_messages)
        )


def test_agent_fallback_parameters_in_sync():
    """
    Test that parameters in sdk/manual/agent_fallback.mdx are synchronized with
    the source parameters in sdk/remoteagentfallback/__init__.mdx
    """
    agent_fallback_file = SDK_DIR / "manual" / "agent_fallback.mdx"
    factory_file = SDK_DIR / "remoteagentfallback" / "__init__.mdx"

    assert agent_fallback_file.exists(), f"Agent fallback file not found: {agent_fallback_file}"
    assert factory_file.exists(), f"Factory file not found: {factory_file}"

    agent_fallback_content = agent_fallback_file.read_text("utf-8")
    factory_content = factory_file.read_text("utf-8")

    # Extract parameter sections from both files
    agent_fallback_params = extract_param_fields(agent_fallback_content)
    factory_params = extract_param_fields(factory_content)

    # Compare the normalized parameter lists
    missing_in_agent_fallback = set(factory_params) - set(agent_fallback_params)
    extra_in_agent_fallback = set(agent_fallback_params) - set(factory_params)

    error_messages = []
    if missing_in_agent_fallback:
        error_messages.append(f"Parameters missing in agent_fallback.mdx: {missing_in_agent_fallback}")
    if extra_in_agent_fallback:
        error_messages.append(f"Extra parameters in agent_fallback.mdx: {extra_in_agent_fallback}")

    if error_messages:
        pytest.fail(
            f"Parameter synchronization failed between {agent_fallback_file} and {factory_file}:\n"
            + "\n".join(error_messages)
        )
