# @sniptest filename=greet_function.py
def run(name: str, greeting: str = "Hello"):
    """
    Greet someone by name.

    Args:
        name: The person's name
        greeting: The greeting word (default: "Hello")

    Returns:
        A personalized greeting
    """
    return f"{greeting}, {name}!"
