from pygments.lexers import guess_lexer
from pygments.util import ClassNotFound


def is_code(text: str) -> bool:
    """
    Determines if a given text is likely to be code by attempting to detect its programming language.

    Args:
        text: The text to analyze

    Returns:
        bool: True if the text appears to be code, False otherwise
    """
    if not text or text.isspace():
        return False

    try:
        lexer = guess_lexer(text)
        return str(lexer) != "<pygments.lexers.TextLexer>" and str(lexer) != "<pygments.lexers.CbmBasicV2Lexer>"
    except ClassNotFound:
        return False
