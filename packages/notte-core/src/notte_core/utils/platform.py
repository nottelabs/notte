from typing import Literal


def platform_control_key() -> Literal["Meta", "Control"]:
    """
    Returns the platform-specific control key modifier.

    Returns:
        Literal["Meta", "Control"]: "Meta" for macOS (Darwin), "Control" for other platforms
    """
    import platform

    return "Meta" if platform.system() == "Darwin" else "Control"
