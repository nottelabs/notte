# @sniptest filename=handler_function.py
# @sniptest show=5-18


def perform_automation(param1: str, param2: int) -> str:
    return f"Result: {param1}, {param2}"


def run(param1: str, param2: int = 10):
    """
    Function docstring explains what it does.

    Args:
        param1: Description of param1
        param2: Description of param2 (optional)

    Returns:
        Description of return value
    """
    # Your automation code
    result = perform_automation(param1, param2)
    return result
