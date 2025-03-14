def text_contains_tabs(text: str) -> bool:
    """
    Determine if a given text has significant indentation patterns.

    Args:
        text (str): The text to analyze

    Returns:
        bool: True if the text has significant indentation patterns, False otherwise
    """
    if not text or text.isspace():
        return False

    # Split into lines and remove empty lines
    lines = [line for line in text.split("\n") if line.strip()]
    if not lines:
        return False

    # Count lines with leading whitespace or tabs
    indented_lines: int = sum(1 for line in lines if line.startswith((" ", "\t")))

    return indented_lines >= 1
