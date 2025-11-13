import pathlib
from typing import Any, final

import pytest
from notte_core.ast import (
    MissingRunFunctionError,
    NotteModule,
    ParsedScriptInfo,
    ScriptValidator,
    SecureScriptRunner,
)

import notte

SAMPLE_SCRIPT_PATH = pathlib.Path(__file__).parent / "sample_script.py"
assert SAMPLE_SCRIPT_PATH.exists(), f"Sample script not found at {SAMPLE_SCRIPT_PATH}"


@pytest.fixture
def mock_notte() -> NotteModule:
    @final
    class MockNotte:
        @final
        class Session:
            def __init__(self, headless: bool = True):
                self.headless = headless

            def __enter__(self):
                return MockSession()

            def __exit__(self, *args):
                pass

        # Add Session as an alias to Script
        Session = Session

        @final
        class AgentFallback:
            def __init__(self, session: Any, name: str):
                self.session = session
                self.name = name
                self.success = True

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        @final
        class Agent:
            def __init__(self, *args, **kwargs):
                pass

            def run(self, *args, **kwargs):
                pass

    class MockSession:
        def execute(self, **kwargs):
            print(f"Executing: {kwargs}")
            return "result"

        def observe(self):
            print("Observing...")
            return "observation"

    return MockNotte()


@pytest.fixture
def test_script() -> str:
    return """
def run():
    url = "https://shop.notte.cc/"
    with notte.Session(headless=True) as session:
        logger.info("Starting script execution")

        result = session.execute(type="goto", value=url)
        obs = session.observe()

        # Test safe built-ins
        url_length = len(url)
        logger.debug(f"URL length: {url_length}")

        with notte.AgentFallback(session, "Add Cap to cart") as chapter:
            logger.info("Starting chapter: Add Cap to cart")
            session.execute(type="click", id="L7")
            session.execute(type="click", id="X1")
            logger.success("Chapter completed successfully")

        assert chapter.success is True
        logger.info("Script execution completed")
"""


# Example usage:
def test_script_runner(mock_notte: NotteModule, test_script: str):
    # Mock notte module for demonstration

    runner = SecureScriptRunner(mock_notte)
    runner.run_script(test_script)


def test_script_validator(test_script: str):
    validator = ScriptValidator()
    _ = validator.parse_script(test_script)


# ===== VALID SCRIPT TESTS =====


def test_basic_valid_script():
    """Test basic valid script with session operations"""
    script = """
def run():
    with notte.Session() as session:
        session.execute(type="goto", value="https://example.com")
        result = session.observe()
"""
    validator = ScriptValidator()
    _ = validator.parse_script(script)


def test_f_string_usage():
    """Test f-string validation"""
    script = """
def run():
    with notte.Session() as session:
        url = "https://example.com"
        logger.info(f"Navigating to {url}")
        session.execute(type="goto", value=url)
"""
    validator = ScriptValidator()
    _ = validator.parse_script(script)


def test_safe_builtin_functions():
    """Test safe built-in functions"""
    script = """
def run():
    with notte.Session() as session:
        url = "https://example.com"
        url_length = len(url)
        url_str = str(url)
        url_int = int("123")
        url_float = float("123.45")
        url_bool = bool(url)
        url_list = list([1, 2, 3])
        url_dict = dict(a=1, b=2)
        url_tuple = tuple([1, 2, 3])
        url_set = set([1, 2, 3])

"""
    validator = ScriptValidator()
    _ = validator.parse_script(script)


def test_control_flow():
    """Test control flow statements"""
    script = """
def run():
    with notte.Session() as session:
        if True:
            session.execute(type="goto", value="https://example.com")

        for i in range(3):
            session.execute(type="click", id=f"button_{i}")

        while False:
            session.observe()

"""
    validator = ScriptValidator()
    _ = validator.parse_script(script)


def test_collections():
    """Test collection operations"""
    script = """
def run():
    with notte.Session() as session:
        my_list = [1, 2, 3]
        my_dict = {"a": 1, "b": 2}
        my_tuple = (1, 2, 3)
        my_set = {1, 2, 3}

        list_comp = [x for x in my_list if x > 1]
        dict_comp = {"a": 1, "b": 2}  # Simple dict instead of comprehension
        set_comp = {x for x in my_list}

"""
    validator = ScriptValidator()
    _ = validator.parse_script(script)


def test_comparisons():
    """Test comparison operators"""
    script = """
def run():
    with notte.Session() as session:
        a = 1
        b = 2

        eq = a == b
        ne = a != b
        lt = a < b
        le = a <= b
        gt = a > b
        ge = a >= b
        is_true = a is True
        is_not = a is not None
        in_list = a in [1, 2, 3]
        not_in = a not in [4, 5, 6]

"""
    validator = ScriptValidator()
    _ = validator.parse_script(script)


def test_mathematical_operations():
    """Test mathematical operations"""
    script = """
def run():
    with notte.Session() as session:
        a = 10
        b = 3

        add = a + b
        sub = a - b
        mult = a * b
        div = a / b
        mod = a % b

"""
    validator = ScriptValidator()
    _ = validator.parse_script(script)


def test_boolean_operations():
    """Test boolean operations"""
    script = """
def run():
    with notte.Session() as session:
        a = True
        b = False

        and_result = a and b
        or_result = a or b
        not_result = not a

"""
    validator = ScriptValidator()
    _ = validator.parse_script(script)


# ===== INVALID SCRIPT TESTS - FORBIDDEN AST NODES =====


def test_import_statement_forbidden():
    """Test that forbidden import statements are rejected"""
    script = """
def run():
    import os
    with notte.Session() as session:
        session.execute(type="goto", value="https://example.com")

"""
    validator = ScriptValidator()
    with pytest.raises(SyntaxError, match="Import of 'os' is not allowed"):
        _ = validator.parse_script(script)


def test_import_from_forbidden():
    """Test that forbidden from import statements are rejected"""
    script = """
def run():
    from os import path
    with notte.Session() as session:
        session.execute(type="goto", value="https://example.com")

"""
    validator = ScriptValidator()
    with pytest.raises(SyntaxError, match="Import from 'os' is not allowed"):
        _ = validator.parse_script(script)


def test_allowed_imports():
    """Test that allowed imports work correctly"""
    script = """
def run():
    import json
    import datetime
    import notte
    from pydantic import BaseModel
    from typing import Dict, List

    with notte.Session() as session:
        data = json.dumps({"timestamp": datetime.datetime.now().isoformat()})
        session.execute(type="goto", value="https://example.com")

"""
    validator = ScriptValidator()
    # Should not raise any exceptions
    _ = validator.parse_script(script)


def test_relative_imports_forbidden():
    """Test that relative imports are not allowed"""
    script = """
def run():
    from . import something
    with notte.Session() as session:
        session.execute(type="goto", value="https://example.com")

"""
    validator = ScriptValidator()
    with pytest.raises(SyntaxError, match="Relative imports are not allowed"):
        _ = validator.parse_script(script)


@pytest.mark.skip(reason="Function definitions are now allowed in scripts")
def test_function_definition_forbidden():
    """Test that function definitions other than 'run' are forbidden"""
    script = """
def run():
    def my_function():
        return "hello"

    with notte.Session() as session:
        session.execute(type="goto", value="https://example.com")

"""
    validator = ScriptValidator()
    with pytest.raises(SyntaxError, match="Only the 'run' function is allowed in Notte scripts, found: 'my_function'"):
        _ = validator.parse_script(script)


@pytest.mark.skip(reason="Class definitions are now allowed in scripts")
def test_class_definition_forbidden():
    """Test that class definitions are forbidden"""
    script = """
def run():
    class MyClass:
        pass

    with notte.Session() as session:
        session.execute(type="goto", value="https://example.com")

"""
    validator = ScriptValidator()
    with pytest.raises(SyntaxError, match="Forbidden AST node in Notte script: ClassDef"):
        _ = validator.parse_script(script)


def test_lambda_forbidden():
    """Test that lambda expressions are forbidden"""
    script = """
def run():
    with notte.Session() as session:
        func = lambda x: x + 1
        session.execute(type="goto", value="https://example.com")

"""
    validator = ScriptValidator()
    with pytest.raises(SyntaxError, match="Forbidden AST node in Notte script: Lambda"):
        _ = validator.parse_script(script)


@pytest.mark.skip(reason="Try/except blocks are allowed in scripts")
def test_try_except_forbidden():
    """Test that try/except blocks are forbidden"""
    script = """
def run():
    with notte.Session() as session:
        try:
            session.execute(type="goto", value="https://example.com")
        except:
            pass

"""
    validator = ScriptValidator()
    with pytest.raises(SyntaxError, match="Forbidden AST node in Notte script: Try"):
        _ = validator.parse_script(script)


def test_delete_forbidden():
    """Test that delete operations are forbidden"""
    script = """
def run():
    with notte.Session() as session:
        x = 1
        del x
        session.execute(type="goto", value="https://example.com")

"""
    validator = ScriptValidator()
    with pytest.raises(SyntaxError, match="Forbidden AST node in Notte script: Delete"):
        _ = validator.parse_script(script)


@pytest.mark.skip(reason="Augmented assignments are now allowed in scripts")
def test_augmented_assignment_forbidden():
    """Test that augmented assignments are forbidden"""
    script = """
def run():
    with notte.Session() as session:
        x = 1
        x += 1
        session.execute(type="goto", value="https://example.com")

"""
    validator = ScriptValidator()
    with pytest.raises(SyntaxError, match="Forbidden AST node in Notte script: AugAssign"):
        _ = validator.parse_script(script)


# ===== INVALID SCRIPT TESTS - FORBIDDEN FUNCTION CALLS =====


def test_dangerous_builtins_forbidden():
    """Test that dangerous built-in functions are forbidden"""
    script = """
def run():
    with notte.Session() as session:
        open("file.txt")
        session.execute(type="goto", value="https://example.com")

"""
    validator = ScriptValidator()
    with pytest.raises(SyntaxError, match="Forbidden function call: 'open'"):
        _ = validator.parse_script(script)


def test_eval_forbidden():
    """Test that eval is forbidden"""
    script = """
def run():
    with notte.Session() as session:
        eval("print('hello')")
        session.execute(type="goto", value="https://example.com")

"""
    validator = ScriptValidator()
    with pytest.raises(SyntaxError, match="Forbidden function call: 'eval'"):
        _ = validator.parse_script(script)


# ===== INVALID SCRIPT TESTS - FORBIDDEN ATTRIBUTE ACCESS =====


def test_private_attribute_forbidden():
    """Test that private attributes are forbidden"""
    script = """
def run():
    with notte.Session() as session:
        session.__class__
        session.execute(type="goto", value="https://example.com")

"""
    validator = ScriptValidator()
    with pytest.raises(SyntaxError, match="Access to private attribute forbidden: '__class__'"):
        _ = validator.parse_script(script)


def test_private_attribute_on_other_objects():
    """Test that private attributes on other objects are forbidden"""
    script = """
def run():
    with notte.Session() as session:
        obj = object()
        obj._private_attr
        session.execute(type="goto", value="https://example.com")

"""
    validator = ScriptValidator()
    with pytest.raises(SyntaxError, match="Access to private attribute forbidden: '_private_attr'"):
        _ = validator.parse_script(script)


# ===== EDGE CASES =====


def test_empty_script_forbidden():
    """Test that empty scripts are forbidden"""
    script = ""
    validator = ScriptValidator()
    with pytest.raises(MissingRunFunctionError, match="Python script must contain a 'run' function"):
        _ = validator.parse_script(script)


def test_whitespace_only_script_forbidden():
    """Test that scripts with only whitespace are forbidden"""
    script = "   \n\t   \n"
    validator = ScriptValidator()
    with pytest.raises(MissingRunFunctionError, match="Python script must contain a 'run' function"):
        _ = validator.parse_script(script)


def test_comments_only_script_forbidden():
    """Test that scripts with only comments are forbidden"""
    script = "# This is a comment\n# Another comment"
    validator = ScriptValidator()
    with pytest.raises(MissingRunFunctionError, match="Python script must contain a 'run' function"):
        _ = validator.parse_script(script)


def test_only_non_notte_operations_forbidden():
    """Test that scripts with only non-notte operations are forbidden"""
    script = """
def run():
    x = 1
    y = 2
    result = x + y
    logger.info("Hello world")

"""
    validator = ScriptValidator()
    with pytest.raises(ValueError, match="Python script must contain at least one notte operation"):
        _ = validator.parse_script(script)


def test_syntax_error():
    """Test that syntax errors are caught"""
    script = """
def run():
    with notte.Session() as session:
        session.execute(type="goto", value="https://example.com"
        # Missing closing parenthesis

"""
    validator = ScriptValidator()
    with pytest.raises(SyntaxError, match="'\\(' was never closed"):
        _ = validator.parse_script(script)


def test_run_script_with_agent():
    script = SAMPLE_SCRIPT_PATH.read_text()
    runner = SecureScriptRunner(notte)
    resp = runner.run_script(script)
    assert resp is not None
    assert isinstance(resp, str)
    assert len(resp) > 0, "Script should return a string"


def test_missing_run_function():
    """Test that scripts without a 'run' function raise MissingRunFunctionError"""
    script_without_run = """
def some_other_function():
    with notte.Session() as session:
        session.execute({"type": "goto", "url": "https://example.com"})
"""
    validator = ScriptValidator()
    with pytest.raises(MissingRunFunctionError, match="Python script must contain a 'run' function"):
        validator.parse_script(script_without_run)


@pytest.mark.skip(reason="Function definitions are now allowed in scripts")
def test_invalid_function_name():
    """Test that functions other than 'run' are not allowed"""
    script_with_invalid_function = """
def invalid_function():
    pass

def run():
    with notte.Session() as session:
        session.execute({"type": "goto", "url": "https://example.com"})
"""
    validator = ScriptValidator()
    with pytest.raises(
        SyntaxError, match="Only the 'run' function is allowed in Notte scripts, found: 'invalid_function'"
    ):
        validator.parse_script(script_with_invalid_function)


# ===== PARAMETER EXTRACTION AND VALIDATION TESTS =====


def test_parameter_extraction_no_params():
    """Test parameter extraction from run function with no parameters"""
    script = """
def run():
    with notte.Session() as session:
        session.execute(type="goto", value="https://example.com")
"""
    validator = ScriptValidator()
    result = validator.parse_script(script, restricted=False)

    assert isinstance(result, ParsedScriptInfo)
    assert len(result.variables) == 0


def test_parameter_extraction_typed_params():
    """Test parameter extraction with typed parameters"""
    script = """
def run(name: str, age: int, city: str):
    with notte.Session() as session:
        session.execute(type="goto", value=f"https://example.com/{name}")
"""
    validator = ScriptValidator()
    result = validator.parse_script(script, restricted=False)

    assert isinstance(result, ParsedScriptInfo)
    assert len(result.variables) == 3

    name_param = result.variables[0]
    assert name_param.name == "name"
    assert name_param.type == "str"
    assert name_param.default is None

    age_param = result.variables[1]
    assert age_param.name == "age"
    assert age_param.type == "int"
    assert age_param.default is None

    city_param = result.variables[2]
    assert city_param.name == "city"
    assert city_param.type == "str"
    assert city_param.default is None


def test_parameter_extraction_with_defaults():
    """Test parameter extraction with default values"""
    script = """
def run(name: str, age: int = 25, city: str = 'New York', optional_param=None):
    with notte.Session() as session:
        session.execute(type="goto", value=f"https://example.com/{name}")
"""
    validator = ScriptValidator()
    result = validator.parse_script(script, restricted=False)

    assert isinstance(result, ParsedScriptInfo)
    assert len(result.variables) == 4

    name_param = result.variables[0]
    assert name_param.name == "name"
    assert name_param.type == "str"
    assert name_param.default is None  # Required parameter

    age_param = result.variables[1]
    assert age_param.name == "age"
    assert age_param.type == "int"
    assert age_param.default == "25"

    city_param = result.variables[2]
    assert city_param.name == "city"
    assert city_param.type == "str"
    assert city_param.default == "'New York'"

    optional_param = result.variables[3]
    assert optional_param.name == "optional_param"
    assert optional_param.type is None
    assert optional_param.default == "None"


def test_parameter_extraction_keyword_only():
    """Test parameter extraction with keyword-only parameters"""
    script = """
def run(name: str, *, age: int = 25, required_kw: str, optional_kw: bool = True):
    with notte.Session() as session:
        session.execute(type="goto", value=f"https://example.com/{name}")
"""
    validator = ScriptValidator()
    result = validator.parse_script(script, restricted=False)

    assert isinstance(result, ParsedScriptInfo)
    assert len(result.variables) == 4

    name_param = result.variables[0]
    assert name_param.name == "name"
    assert name_param.type == "str"
    assert name_param.default is None

    age_param = result.variables[1]
    assert age_param.name == "age"
    assert age_param.type == "int"
    assert age_param.default == "25"

    required_kw_param = result.variables[2]
    assert required_kw_param.name == "required_kw"
    assert required_kw_param.type == "str"
    assert required_kw_param.default is None  # Required keyword-only parameter

    optional_kw_param = result.variables[3]
    assert optional_kw_param.name == "optional_kw"
    assert optional_kw_param.type == "bool"
    assert optional_kw_param.default == "True"


def test_parameter_extraction_untyped_params():
    """Test parameter extraction with untyped parameters"""
    script = """
def run(name, age=25, city='Default'):
    with notte.Session() as session:
        session.execute(type="goto", value=f"https://example.com/{name}")
"""
    validator = ScriptValidator()
    result = validator.parse_script(script, restricted=False)

    assert isinstance(result, ParsedScriptInfo)
    assert len(result.variables) == 3

    name_param = result.variables[0]
    assert name_param.name == "name"
    assert name_param.type is None
    assert name_param.default is None

    age_param = result.variables[1]
    assert age_param.name == "age"
    assert age_param.type is None
    assert age_param.default == "25"

    city_param = result.variables[2]
    assert city_param.name == "city"
    assert city_param.type is None
    assert city_param.default == "'Default'"


def test_parameter_validation_valid_variables(mock_notte: NotteModule):
    """Test parameter validation with valid variables"""
    script = """
def run(name: str, age: int = 25, city: str = 'NYC'):
    with notte.Session() as session:
        session.execute(type="goto", value=f"https://example.com/{name}")
        return f"Hello {name}, age {age}, city {city}"
"""
    runner = SecureScriptRunner(mock_notte)

    # Test with all parameters
    result = runner.run_script(script, {"name": "Alice", "age": 30, "city": "Boston"}, restricted=False)
    assert result == "Hello Alice, age 30, city Boston"

    # Test with only required parameter
    result = runner.run_script(script, {"name": "Bob"}, restricted=False)
    assert result == "Hello Bob, age 25, city NYC"

    # Test with some optional parameters
    result = runner.run_script(script, {"name": "Charlie", "age": 35}, restricted=False)
    assert result == "Hello Charlie, age 35, city NYC"


def test_parameter_validation_missing_required(mock_notte: NotteModule):
    """Test parameter validation with missing required parameters"""
    script = """
def run(name: str, age: int = 25):
    with notte.Session() as session:
        session.execute(type="goto", value=f"https://example.com/{name}")
        return f"Hello {name}, age {age}"
"""
    runner = SecureScriptRunner(mock_notte)

    # Missing required parameter 'name'
    with pytest.raises(ValueError, match="Missing required parameters for run function: \\['name'\\]"):
        runner.run_script(script, {"age": 30}, restricted=False)

    # No variables provided at all
    with pytest.raises(ValueError, match="Missing required parameters for run function: \\['name'\\]"):
        runner.run_script(script, {}, restricted=False)


def test_parameter_validation_unexpected_parameters(mock_notte: NotteModule):
    """Test parameter validation with unexpected parameters"""
    script = """
def run(name: str, age: int = 25):
    with notte.Session() as session:
        session.execute(type="goto", value=f"https://example.com/{name}")
        return f"Hello {name}, age {age}"
"""
    runner = SecureScriptRunner(mock_notte)

    # Unexpected parameter 'height'
    with pytest.raises(ValueError, match="Unexpected variable names for run function: \\['height'\\]"):
        runner.run_script(script, {"name": "Alice", "height": 180}, restricted=False)

    # Multiple unexpected parameters
    with pytest.raises(ValueError, match="Unexpected variable names for run function: \\['height', 'weight'\\]"):
        runner.run_script(script, {"name": "Bob", "height": 180, "weight": 75}, restricted=False)


def test_parameter_validation_keyword_only_params(mock_notte: NotteModule):
    """Test parameter validation with keyword-only parameters"""
    script = """
def run(name: str, *, age: int = 25, required_kw: str):
    with notte.Session() as session:
        session.execute(type="goto", value=f"https://example.com/{name}")
        return f"Hello {name}, age {age}, required_kw {required_kw}"
"""
    runner = SecureScriptRunner(mock_notte)

    # Valid with all parameters
    result = runner.run_script(script, {"name": "Alice", "age": 30, "required_kw": "test"}, restricted=False)
    assert result == "Hello Alice, age 30, required_kw test"

    # Valid with only required parameters
    result = runner.run_script(script, {"name": "Bob", "required_kw": "test"}, restricted=False)
    assert result == "Hello Bob, age 25, required_kw test"

    # Missing required keyword-only parameter
    with pytest.raises(ValueError, match="Missing required parameters for run function: \\['required_kw'\\]"):
        runner.run_script(script, {"name": "Charlie"}, restricted=False)


def test_parameter_validation_multiple_required_missing(mock_notte: NotteModule):
    """Test parameter validation with multiple missing required parameters"""
    script = """
def run(name: str, email: str, age: int = 25):
    with notte.Session() as session:
        session.execute(type="goto", value=f"https://example.com/{name}")
        return f"Hello {name}, email {email}, age {age}"
"""
    runner = SecureScriptRunner(mock_notte)

    # Missing multiple required parameters
    with pytest.raises(ValueError, match="Missing required parameters for run function: \\['email', 'name'\\]"):
        runner.run_script(script, {"age": 30}, restricted=False)


def test_parameter_validation_empty_variables(mock_notte: NotteModule):
    """Test parameter validation with empty variables dict"""
    script = """
def run(name: str = 'Default'):
    with notte.Session() as session:
        session.execute(type="goto", value=f"https://example.com/{name}")
        return f"Hello {name}"
"""
    runner = SecureScriptRunner(mock_notte)

    # Should work with empty dict when all parameters have defaults
    result = runner.run_script(script, {}, restricted=False)
    assert result == "Hello Default"

    # Should also work with None variables
    result = runner.run_script(script, None, restricted=False)
    assert result == "Hello Default"


def test_parameter_validation_complex_types():
    """Test parameter extraction with complex type annotations"""
    script = """
from typing import Dict, List, Optional
def run(data: Dict[str, int], items: List[str], optional: Optional[bool] = None):
    with notte.Session() as session:
        session.execute(type="goto", value="https://example.com")
"""
    validator = ScriptValidator()
    result = validator.parse_script(script, restricted=False)

    assert isinstance(result, ParsedScriptInfo)
    assert len(result.variables) == 3

    data_param = result.variables[0]
    assert data_param.name == "data"
    assert data_param.type == "Dict[str, int]"
    assert data_param.default is None

    items_param = result.variables[1]
    assert items_param.name == "items"
    assert items_param.type == "List[str]"
    assert items_param.default is None

    optional_param = result.variables[2]
    assert optional_param.name == "optional"
    assert optional_param.type == "Optional[bool]"
    assert optional_param.default == "None"


def test_parameter_validation_restricted_mode(mock_notte: NotteModule):
    """Test parameter validation works in restricted mode"""
    script = """
def run(name: str, age: int = 25):
    with notte.Session() as session:
        session.execute(type="goto", value=f"https://example.com/{name}")
        return f"Hello {name}, age {age}"
"""
    runner = SecureScriptRunner(mock_notte)

    # Valid parameters in restricted mode
    result = runner.run_script(script, {"name": "Alice"}, restricted=True)
    assert result == "Hello Alice, age 25"

    # Invalid parameters in restricted mode
    with pytest.raises(ValueError, match="Missing required parameters for run function: \\['name'\\]"):
        runner.run_script(script, {"age": 30}, restricted=True)


def test_parameter_extraction_run_function_without_parameters_type():
    """Test parameter extraction when run function has no return type annotation"""
    script = """
def run(name, age = 25):
    with notte.Session() as session:
        session.execute(type="goto", value=f"https://example.com/{name}")
        return f"Hello {name}, age {age}"
"""
    validator = ScriptValidator()
    result = validator.parse_script(script, restricted=False)

    assert isinstance(result, ParsedScriptInfo)
    assert len(result.variables) == 2

    name_param = result.variables[0]
    assert name_param.name == "name"
    assert name_param.type is None
    assert name_param.default is None

    age_param = result.variables[1]
    assert age_param.name == "age"
    assert age_param.type is None
    assert age_param.default == "25"
