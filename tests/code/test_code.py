from notte_core.utils.code import text_contains_tabs


def test_positive_indentation_examples():
    # Simple indented text
    assert text_contains_tabs("""
    This line is indented
        This one even more
    Back to first level
""")

    # Mixed indentation levels
    assert text_contains_tabs("""
    First level
        Second level
            Third level
        Back to second
    First again
""")

    # Single indented line
    assert text_contains_tabs("""
Normal line
    This one is indented
Another normal line
""")


def test_negative_examples():
    # Empty string
    assert not text_contains_tabs("")

    # Simple text without indentation
    assert not text_contains_tabs("Hello World!")

    # Multi-line text without indentation
    assert not text_contains_tabs("""
This text has multiple lines
But none of them are indented
They just flow normally
Without any special spacing
""")


def test_mixed_content():
    # Text with one indented line
    assert text_contains_tabs("""
Here is some text
    This line is special because it's indented
But the rest is normal
""")

    # List-like text with indentation
    assert text_contains_tabs("""
Items in a list:
    1. First item
    2. Second item
    3. Third item
""")

    # Quoted text with indentation
    assert text_contains_tabs("""
Someone said:
    This is a famous quote
    That spans multiple lines
    With consistent indentation
""")


def test_edge_cases():
    # Whitespace only
    assert not text_contains_tabs("   \n   \t   ")

    # Single line with spaces but no newlines
    assert text_contains_tabs("    just spaces")

    # Numbers only
    assert not text_contains_tabs("12345 67890")
