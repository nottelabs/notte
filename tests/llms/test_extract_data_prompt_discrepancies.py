from pathlib import Path

import pytest

from tests.llms.test_action_listing_prompt_discrepancies import extract_section, format_diff_message, read_file_content


@pytest.fixture
def prompt_contents() -> dict[str, str]:
    """Fixture to load both prompt files"""
    current_dir: Path = Path(__file__).parent
    project_root: Path = current_dir.parent.parent

    raw_path: Path = project_root / "packages/notte-core/src/notte_core/llms/prompts/data-extraction/all_data/user.md"
    relevant_path: Path = (
        project_root / "packages/notte-core/src/notte_core/llms/prompts/data-extraction/only_main_content/user.md"
    )

    return {
        "raw": read_file_content(raw_path),
        "relevant": read_file_content(relevant_path),
    }


def test_intro_section(prompt_contents: dict[str, str]) -> None:
    raw_intro: str = extract_section(prompt_contents["raw"], "You are an expert", "1. `<document-category>`:")
    relevant_intro: str = extract_section(prompt_contents["relevant"], "You are an expert", "1. `<document-category>`:")

    assert raw_intro.strip() == relevant_intro.strip(), (
        f"Intro sections differ:{format_diff_message(raw_intro.strip(), relevant_intro.strip())}"
    )


def test_document_category_section(prompt_contents: dict[str, str]) -> None:
    raw_category: str = extract_section(
        prompt_contents["raw"], "1. `<document-category>`:", "2. `<document-analysis>`:"
    )
    relevant_category: str = extract_section(
        prompt_contents["relevant"],
        "1. `<document-category>`:",
        "2. `<document-analysis>`:",
    )

    assert raw_category.strip() == relevant_category.strip(), (
        f"Document Category sections differ:{format_diff_message(raw_category.strip(), relevant_category.strip())}"
    )


def test_document_analysis_section(prompt_contents: dict[str, str]) -> None:
    raw_analysis: str = extract_section(prompt_contents["raw"], "2. `<document-analysis>`:", "3. `<data-extraction>`:")
    relevant_analysis: str = extract_section(
        prompt_contents["relevant"],
        "2. `<document-analysis>`:",
        "3. `<data-extraction>`:",
    )

    # Remove the incremental-specific text from comparison
    relevant_analysis_base: str = (
        relevant_analysis.replace(
            "- Step 2: Decide Section Relevance. For each identified section, decide if the section is relevant to ",
            "",
        )
        .replace(
            """the document's purpose based on its main content.
* Relevant: Includes sections containing the document's key information.
* Not Relevant: Exclude elements like login areas, navigation menus, """,
            "",
        )
        .replace(
            """or contact information or social media links unless essential to the main purpose.
""",
            "",
        )
        .replace(
            "- Step 3: Capture relevant elements. For each relevant section",
            "- Step 2: For each identified section",
        )
        .replace(
            "list ALL relevant elements ",
            "list ALL elements ",
        )
        .replace(
            '```Step 3 - Relevant elements for section "XYZ"',
            '```Step 2 - Elements for section "XYZ"',
        )
        .replace(
            "- Step 4: process relevant elements. For each captured element",
            "- Step 3: For each element",
        )
    )

    assert raw_analysis.strip() == relevant_analysis_base.strip(), (
        f"Document Analysis sections differ:{format_diff_message(raw_analysis.strip(), relevant_analysis_base.strip())}"
    )


def test_data_extraction_section(prompt_contents: dict[str, str]) -> None:
    raw_extraction: str = extract_section(prompt_contents["raw"], "3. `<data-extraction>`:", "# Critical Rules:")
    relevant_extraction: str = extract_section(
        prompt_contents["relevant"], "3. `<data-extraction>`:", "# Critical Rules:"
    )

    relevant_extraction_base: str = relevant_extraction.replace(
        "captured relevant ",
        "",
    )
    assert raw_extraction.strip() == relevant_extraction_base.strip(), (
        f"Data Extraction sectio differ:{format_diff_message(raw_extraction.strip(), relevant_extraction_base.strip())}"
    )


def test_critical_rules_section(prompt_contents: dict[str, str]) -> None:
    raw_rules: str = extract_section(prompt_contents["raw"], "# Critical Rules:", "# Example outputs:")
    relevant_rules: str = extract_section(prompt_contents["relevant"], "# Critical Rules:", "# Example outputs:")

    assert raw_rules.strip() == relevant_rules.strip(), (
        f"Critical Rules sections differ:{format_diff_message(raw_rules.strip(), relevant_rules.strip())}"
    )


def test_example_outputs_section(prompt_contents: dict[str, str]) -> None:
    raw_outputs: str = extract_section(prompt_contents["raw"], "# Example outputs:", "# Final Reminders:")
    relevant_outputs: str = extract_section(prompt_contents["relevant"], "# Example outputs:", "# Final Reminders:")

    assert raw_outputs.strip() == relevant_outputs.strip(), (
        f"Example outputs sections differ:{format_diff_message(raw_outputs.strip(), relevant_outputs.strip())}"
    )


def test_final_reminders_section(prompt_contents: dict[str, str]) -> None:
    raw_reminders: str = extract_section(prompt_contents["raw"], "# Final Reminders:", "")
    relevant_reminders: str = extract_section(prompt_contents["relevant"], "# Final Reminders:", "")
    relevant_reminder_base: str = (
        relevant_reminders.replace(
            "- DO NOT include unrelevant elements in the output, such as "
            "login areas, navigation menus, or contact information ",
            "",
        )
        .replace(
            """or social media links unless essential to the main purpose.
""",
            "",
        )
        .replace("- ALL remaining textual content", "- ALL textual content")
    )
    assert raw_reminders.strip() == relevant_reminder_base.strip(), (
        f"Final Reminders sections differ:{format_diff_message(raw_reminders.strip(), relevant_reminder_base.strip())}"
    )
