"""
Test that all action classes are properly imported and aliased in notte.actions.
"""

import pytest


def test_all_renamed_actions_are_imported():
    """Test that all expected renamed action classes are imported and accessible."""
    # Import the actions module
    import notte.actions as actions_module

    # Expected renamed action classes (without 'Action' suffix)
    expected_renamed_classes: list[str] = [
        "FormFill",
        "Goto",
        "GotoNewTab",
        "CloseTab",
        "SwitchTab",
        "GoBack",
        "GoForward",
        "Reload",
        "Wait",
        "PressKey",
        "ScrollUp",
        "ScrollDown",
        "CaptchaSolve",
        "Help",
        "Completion",
        "Scrape",
        "EmailRead",
        "SmsRead",
        "Click",
        "Fill",
        "MultiFactorFill",
        "FallbackFill",
        "Check",
        "SelectDropdownOption",
        "UploadFile",
        "DownloadFile",
    ]

    missing_classes: list[str] = []

    # Check that all renamed classes are available
    for class_name in expected_renamed_classes:
        if not hasattr(actions_module, class_name):
            missing_classes.append(class_name)

    assert not missing_classes, f"Missing renamed action classes: {missing_classes}"


def test_renamed_actions_are_proper_classes():
    """Test that all renamed action classes are actual classes."""
    import notte.actions as actions_module

    expected_renamed_classes: list[str] = [
        "FormFill",
        "Goto",
        "GotoNewTab",
        "CloseTab",
        "SwitchTab",
        "GoBack",
        "GoForward",
        "Reload",
        "Wait",
        "PressKey",
        "ScrollUp",
        "ScrollDown",
        "CaptchaSolve",
        "Help",
        "Completion",
        "Scrape",
        "EmailRead",
        "SmsRead",
        "Click",
        "Fill",
        "MultiFactorFill",
        "FallbackFill",
        "Check",
        "SelectDropdownOption",
        "UploadFile",
        "DownloadFile",
    ]

    for class_name in expected_renamed_classes:
        action_class = getattr(actions_module, class_name)
        assert isinstance(action_class, type), f"{class_name} is not a class, got {type(action_class)}"


def test_renamed_actions_can_be_instantiated():
    """Test that renamed action classes can be instantiated with basic parameters."""
    import notte.actions as actions_module

    # Test cases for different action types
    test_cases = [
        # Browser actions
        ("Goto", {"url": "https://example.com"}),
        ("Wait", {"time_ms": 1000}),
        ("PressKey", {"key": "Enter"}),
        ("ScrollUp", {"amount": 100}),
        ("ScrollDown", {"amount": 100}),
        ("Help", {"reason": "Test reason"}),
        ("Completion", {"success": True, "answer": "Test answer"}),
        # Tool actions
        ("Scrape", {"instructions": "Test scrape"}),
        # Interaction actions
        ("Click", {"id": "test-button"}),
        ("Fill", {"id": "test-input", "value": "test value"}),
        ("Check", {"id": "test-checkbox", "value": True}),
    ]

    for class_name, kwargs in test_cases:
        action_class = getattr(actions_module, class_name)
        try:
            instance = action_class(**kwargs)
            assert instance is not None
            assert hasattr(instance, "type")
        except Exception as e:
            pytest.fail(f"Failed to instantiate {class_name} with {kwargs}: {e}")


def test_renamed_actions_have_correct_types():
    """Test that renamed action classes have the correct type field."""
    import notte.actions as actions_module

    # Test a few key actions
    test_cases = [
        ("Goto", "goto"),
        ("Click", "click"),
        ("Fill", "fill"),
        ("Scrape", "scrape"),
        ("Wait", "wait"),
    ]

    for class_name, expected_type in test_cases:
        action_class = getattr(actions_module, class_name)

        # Create a minimal instance to test the type
        if class_name == "Goto":
            instance = action_class(url="https://example.com")
        elif class_name == "Click":
            instance = action_class(id="test")
        elif class_name == "Fill":
            instance = action_class(id="test", value="test")
        elif class_name == "Scrape":
            instance = action_class()
        elif class_name == "Wait":
            instance = action_class(time_ms=1000)
        else:
            continue

        assert instance.type == expected_type, f"{class_name} should have type '{expected_type}', got '{instance.type}'"


def test_original_action_classes_not_exported():
    """Test that original action classes (with 'Action' suffix) are not exported in __all__."""
    import notte.actions as actions_module

    # Get the __all__ list
    all_exports = getattr(actions_module, "__all__", [])

    # Check that no classes with 'Action' suffix are in __all__
    action_suffix_exports = [name for name in all_exports if name.endswith("Action")]

    assert not action_suffix_exports, f"Found original action classes in __all__: {action_suffix_exports}"


def test_renamed_actions_in_all_exports():
    """Test that all renamed action classes are included in __all__."""
    import notte.actions as actions_module

    # Get the __all__ list
    all_exports = getattr(actions_module, "__all__", [])

    expected_renamed_classes: list[str] = [
        "FormFill",
        "Goto",
        "GotoNewTab",
        "CloseTab",
        "SwitchTab",
        "GoBack",
        "GoForward",
        "Reload",
        "Wait",
        "PressKey",
        "ScrollUp",
        "ScrollDown",
        "CaptchaSolve",
        "Help",
        "Completion",
        "Scrape",
        "EmailRead",
        "SmsRead",
        "Click",
        "Fill",
        "MultiFactorFill",
        "FallbackFill",
        "Check",
        "SelectDropdownOption",
        "UploadFile",
        "DownloadFile",
    ]

    missing_from_all = [name for name in expected_renamed_classes if name not in all_exports]

    assert not missing_from_all, f"Missing renamed action classes from __all__: {missing_from_all}"


def test_import_star_works():
    """Test that 'from notte.actions import *' works correctly."""
    # Create a new module namespace
    test_globals = {}

    # Import everything from notte.actions
    exec("from notte.actions import *", test_globals)

    # Check that renamed classes are available
    expected_renamed_classes: list[str] = [
        "FormFill",
        "Goto",
        "GotoNewTab",
        "CloseTab",
        "SwitchTab",
        "GoBack",
        "GoForward",
        "Reload",
        "Wait",
        "PressKey",
        "ScrollUp",
        "ScrollDown",
        "CaptchaSolve",
        "Help",
        "Completion",
        "Scrape",
        "EmailRead",
        "SmsRead",
        "Click",
        "Fill",
        "MultiFactorFill",
        "FallbackFill",
        "Check",
        "SelectDropdownOption",
        "UploadFile",
        "DownloadFile",
    ]

    missing_from_star = [name for name in expected_renamed_classes if name not in test_globals]

    assert not missing_from_star, f"Missing classes when using 'import *': {missing_from_star}"


if __name__ == "__main__":
    # Run tests if executed directly
    pytest.main([__file__, "-v"])
