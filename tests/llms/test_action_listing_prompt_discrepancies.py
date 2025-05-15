import difflib
from pathlib import Path

import pytest


def read_file_content(file_path: Path) -> str:
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def extract_section(content: str, start_marker: str, end_marker: str | None = None) -> str:
    """Extract content between start_marker and end_marker."""
    try:
        start_idx: int = content.index(start_marker)
        if end_marker:
            end_idx: int = content.index(end_marker, start_idx)
            return content[start_idx:end_idx].strip()
        else:
            return content[start_idx:].strip()
    except ValueError:
        return ""


def format_diff_message(optim_text: str, incr_text: str) -> str:
    """Creates a detailed diff message between two texts."""
    diff: list[str] = list(difflib.ndiff(optim_text.splitlines(), incr_text.splitlines()))

    # Collect differences
    only_in_optim: list[str] = []
    only_in_incr: list[str] = []

    for line in diff:
        if line.startswith("- "):
            only_in_optim.append(line[2:])
        elif line.startswith("+ "):
            only_in_incr.append(line[2:])

    message: list[str] = []
    if only_in_optim:
        message.append("\nOnly in optimized prompt:")
        message.extend(f"  {line}" for line in only_in_optim)

    if only_in_incr:
        message.append("\nOnly in incremental prompt:")
        message.extend(f"  {line}" for line in only_in_incr)

    return "\n".join(message)


@pytest.fixture
def prompt_contents() -> dict[str, str]:
    """Fixture to load both prompt files"""
    current_dir: Path = Path(__file__).parent
    project_root: Path = current_dir.parent.parent

    optim_path: Path = project_root / "packages/notte-core/src/notte_core/llms/prompts/action-listing/optim/user.md"
    incr_path: Path = project_root / "packages/notte-core/src/notte_core/llms/prompts/action-listing-incr/user.md"

    return {
        "optim": read_file_content(optim_path),
        "incr": read_file_content(incr_path),
    }


def test_intro_section(prompt_contents: dict[str, str]) -> None:
    optim_intro: str = extract_section(prompt_contents["optim"], "You are an expert", "1. <document-summary>")
    incr_intro: str = extract_section(prompt_contents["incr"], "You are an expert", "1. <document-summary>")

    # Remove the incremental-specific text from comparison
    incr_intro_base: str = incr_intro.replace(
        " based on previously identified actions. "
        "Your goal is to extend the list of actions to cover all "
        "possible user interactions, without duplicating any actions.",
        ".",
    ).replace(", and a list of previously identified actions", "")

    assert optim_intro.strip() == incr_intro_base.strip(), (
        f"Intro sections differ:{format_diff_message(optim_intro.strip(), incr_intro_base.strip())}"
    )


def test_document_summary_section(prompt_contents: dict[str, str]) -> None:
    optim_summary: str = extract_section(prompt_contents["optim"], "1. <document-summary>", "2. <document-analysis>")
    incr_summary: str = extract_section(prompt_contents["incr"], "1. <document-summary>", "2. <document-analysis>")
    assert optim_summary.strip() == incr_summary.strip(), (
        f"Document summary sections differ:{format_diff_message(optim_summary.strip(), incr_summary.strip())}"
    )


def test_document_analysis_section(prompt_contents: dict[str, str]) -> None:
    optim_analysis: str = extract_section(prompt_contents["optim"], "2. <document-analysis>", "3. <action-listing>")
    incr_analysis: str = (
        extract_section(prompt_contents["incr"], "2. <document-analysis>", "3. <action-listing>")
        .replace(" that have not been previously identified", "")
        .replace(
            """- Compare the provided previous action list against the document to identify new or modified actions.
""",
            "",
        )
    )
    assert optim_analysis.strip() == incr_analysis.strip(), (
        f"Document analysis sections differ:{format_diff_message(optim_analysis.strip(), incr_analysis.strip())}"
    )


def test_action_listing_section(prompt_contents: dict[str, str]) -> None:
    optim_listing: str = extract_section(
        prompt_contents["optim"],
        "3. <action-listing>",
        "# Rules for creating the table:",
    )
    incr_listing: str = extract_section(
        prompt_contents["incr"],
        "3. <action-listing>",
        "# Rules for creating the table:",
    )
    assert optim_listing.strip() == incr_listing.strip(), (
        f"Action listing sections differ:{format_diff_message(optim_listing.strip(), incr_listing.strip())}"
    )


def test_rules_section(prompt_contents: dict[str, str]) -> None:
    optim_rules: str = extract_section(prompt_contents["optim"], "# Rules for creating the table:", "# Critical Rules:")
    incr_rules: str = extract_section(prompt_contents["incr"], "# Rules for creating the table:", "# Critical Rules:")
    assert optim_rules.strip() == incr_rules.strip(), (
        f"Rules sections differ:{format_diff_message(optim_rules.strip(), incr_rules.strip())}"
    )


def test_critical_rules_section(prompt_contents: dict[str, str]) -> None:
    optim_critical: str = extract_section(prompt_contents["optim"], "# Critical Rules:", "Example of CORRECT entries:")
    incr_critical: str = extract_section(prompt_contents["incr"], "# Critical Rules:", "Example of CORRECT entries:")
    assert optim_critical.strip() == incr_critical.strip(), (
        f"Critical rules sections differ:{format_diff_message(optim_critical.strip(), incr_critical.strip())}"
    )


def test_examples_section(prompt_contents: dict[str, str]) -> None:
    optim_examples: str = extract_section(prompt_contents["optim"], "Example of CORRECT entries:", "# Example output:")
    incr_examples: str = extract_section(
        prompt_contents["incr"],
        "Example of CORRECT entries:",
        "# ACTION EXTENSION CRITICAL RULES:",
    )
    assert optim_examples.strip() == incr_examples.strip(), (
        f"Examples sections differ:{format_diff_message(optim_examples.strip(), incr_examples.strip())}"
    )


def test_example_output_section(prompt_contents: dict[str, str]) -> None:
    optim_output: str = extract_section(prompt_contents["optim"], "# Example output:", "<document>")
    incr_output: str = extract_section(prompt_contents["incr"], "# Example output:", "<previous-action-list>")
    assert optim_output.strip() == incr_output.strip(), (
        f"Example output sections differ:{format_diff_message(optim_output.strip(), incr_output.strip())}"
    )
