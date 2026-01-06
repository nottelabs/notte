import ast
import traceback
import types
from collections.abc import Mapping
from typing import Any, Callable, ClassVar, Literal, Protocol, final

from pydantic import BaseModel, ConfigDict
from RestrictedPython import compile_restricted, safe_globals  # type: ignore [reportMissingTypeStubs]
from RestrictedPython.transformer import RestrictingNodeTransformer  # type: ignore [reportMissingTypeStubs]
from typing_extensions import override


class MissingRunFunctionError(Exception):
    """Raised when a script does not contain a required 'run' function"""

    pass


class ParameterInfo(BaseModel):
    """Information about a function parameter"""

    name: str
    type: str | None = None
    default: str | None = None


class ParsedScriptInfo(BaseModel):
    """Information extracted from parsing a script"""

    model_config: ClassVar[ConfigDict] = ConfigDict(arbitrary_types_allowed=True)

    code: types.CodeType
    variables: list[ParameterInfo]


class NotteModule(Protocol):
    Chapter: type
    Agent: type
    Session: type


class ScriptValidator(RestrictingNodeTransformer):
    """Validates that the AST only contains allowed operations"""

    # Notte-specific operations that must be present in valid scripts
    NOTTE_OPERATIONS: ClassVar[set[str]] = {"notte.Session", "client.Session", "cli.Session", "c.Session", "n.Session"}

    # Safe modules that can be imported in user scripts
    # These modules are considered safe because they don't provide:
    # - File system access (os, pathlib, shutil)
    # - Process/subprocess control (subprocess, multiprocessing)
    # - Network access beyond basic parsing (socket, urllib.request, http)
    # - System introspection (sys, inspect, importlib)
    # - Code execution (exec, eval, compile - handled separately)
    ALLOWED_IMPORTS: ClassVar[set[str]] = {
        # Notte ecosystem - always safe in this context
        "notte",
        "notte_browser",
        "notte_sdk",
        "notte_agent",
        "notte_core",
        # Safe third-party
        "pydantic",  # Data validation library
        "loguru",  # Logging library
        "requests",
        "asyncio",
        "playwright",
        "gspread",
        "google",
        "litellm",
        # Safe standard library modules - data processing and utilities
        "types",
        "json",  # JSON parsing
        "datetime",  # Date/time handling
        "time",  # Time utilities
        "math",  # Mathematical functions
        "random",  # Random number generation
        "uuid",  # UUID generation
        "re",  # Regular expressions
        "urllib.parse",  # URL parsing only (not requests)
        "base64",  # Base64 encoding/decoding
        "hashlib",  # Cryptographic hashing
        "hmac",  # HMAC operations
        "secrets",  # Secure random generation
        "string",  # String operations
        "collections",  # Collection types
        "itertools",  # Iterator utilities
        "functools",  # Functional programming utilities
        "operator",  # Operator functions
        "copy",  # Object copying
        "decimal",  # Decimal arithmetic
        "fractions",  # Fraction arithmetic
        "statistics",  # Statistical functions
        "enum",  # Enumeration support
        "dataclasses",  # Dataclass support
        "typing",  # Type hints
        "typing_extensions",  # Extended type hints
        "calendar",
        "tempfile",
    }

    FORBIDDEN_NODES: set[type[ast.AST]] = {
        # Dangerous operations - removed ast.Import and ast.ImportFrom to handle separately
        # ast.FunctionDef,  # Allow function definitions but validate them separately
        # ast.AsyncFunctionDef,
        # ast.ClassDef,
        ast.Global,
        ast.Nonlocal,
        # # Allow try/except blocks to be used in scripts
        # # ast.Try,
        # # ast.ExceptHandler,
        ast.TryStar,
        # # Advanced features that could be misused
        ast.Lambda,
        # ast.GeneratorExp,
        # ast.Yield,
        # ast.YieldFrom,
        # ast.Await,
        ast.Delete,
        # ast.AugAssign,
    }

    FORBIDDEN_CALLS: set[str] = {
        "open",
        "input",
        # "print",  # print might be OK depending on your needs
        # "hash",
        "__import__",
        "exec",
        "eval",
        "compile",
        "globals",
        "locals",
        "vars",
        "dir",
        "getattr",
        "setattr",
        "delattr",
        "hasattr",
        "id",
        "memoryview",
    }

    @override
    def visit_Call(self, node: ast.Call) -> ast.AST:
        """Override to add custom call restrictions"""
        call_name = self._get_call_name(node)

        if call_name and call_name in self.FORBIDDEN_CALLS:
            raise SyntaxError(f"Forbidden function call: '{call_name}'")

        return super().visit_Call(node)

    def _get_call_name(self, node: ast.Call) -> str | None:
        """Extract the full call name from a Call node"""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                return f"{node.func.value.id}.{node.func.attr}"
            elif isinstance(node.func.value, ast.Attribute):
                # Handle nested attributes like session.execute
                base = self._get_attr_name(node.func.value)
                return f"{base}.{node.func.attr}" if base else None
        return None

    def _get_attr_name(self, node: ast.Attribute | ast.Name | ast.expr) -> str | None:
        """Get attribute name recursively"""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            base = self._get_attr_name(node.value)
            return f"{base}.{node.attr}" if base else None
        return None

    @override
    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        """Override to add custom attribute access restrictions"""
        # Block access to private attributes
        if hasattr(node, "attr") and node.attr.startswith("_"):
            raise SyntaxError(f"Access to private attribute forbidden: '{node.attr}'")
        return super().visit_Attribute(node)

    @staticmethod
    def check_valid_import(name: str, import_type: Literal["import", "import from"] = "import") -> None:
        # Allow exact matches and explicitly whitelisted submodules
        allowed = name in ScriptValidator.ALLOWED_IMPORTS or any(
            name.startswith(f"{m}.") for m in ScriptValidator.ALLOWED_IMPORTS
        )
        if not allowed:
            raise SyntaxError(
                f"Import {'of' if import_type == 'import' else 'from'} '{name}' is not allowed. Allowed imports: {sorted(ScriptValidator.ALLOWED_IMPORTS)}"
            )

    @override
    def visit_Import(self, node: ast.Import) -> ast.AST:
        """Override to validate allowed imports"""
        for alias in node.names:
            ScriptValidator.check_valid_import(alias.name, import_type="import")
        return super().visit_Import(node)

    @override
    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.AST:
        """Override to validate allowed from imports"""
        if node.module is None:
            raise SyntaxError("Relative imports are not allowed")

        ScriptValidator.check_valid_import(node.module, import_type="import from")
        return super().visit_ImportFrom(node)

    @override
    def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.AST:
        """Override to allow type annotations (useful for response schemas).

        RestrictedPython's default policy forbids AnnAssign.
        - We still visit children to validate annotation expressions.
        """
        _ = self.visit(node.annotation)
        _ = self.visit(node.target)
        if node.value is not None:
            _ = self.visit(node.value)
        return node

    @override
    def visit(self, node: ast.AST) -> ast.AST:
        """Override to add custom node restrictions"""
        if type(node) in self.FORBIDDEN_NODES:
            raise SyntaxError(f"Forbidden AST node in Notte script: {type(node).__name__}")
        return super().visit(node)

    @staticmethod
    def _check_run_function_exists(tree: ast.Module) -> bool:
        """Check if the AST contains a function named 'run'"""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "run":
                return True
        return False

    @staticmethod
    def _extract_run_function_parameters(tree: ast.Module) -> list[ParameterInfo]:
        """Extract parameter information from the 'run' function"""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "run":
                parameters: list[ParameterInfo] = []

                # Handle regular arguments
                defaults_offset = len(node.args.args) - len(node.args.defaults)
                for i, arg in enumerate(node.args.args):
                    param_name = arg.arg
                    type_annotation = None
                    default_value = None

                    # Extract type annotation if present
                    if arg.annotation:
                        try:
                            # Use ast.unparse for Python 3.9+ or fallback to basic string representation
                            type_annotation = ast.unparse(arg.annotation)
                        except AttributeError:
                            # Fallback for older Python versions (though we're on 3.11)
                            type_annotation = str(arg.annotation)

                    # Extract default value if present
                    if i >= defaults_offset:
                        default_index = i - defaults_offset
                        if default_index < len(node.args.defaults):
                            try:
                                default_value = ast.unparse(node.args.defaults[default_index])
                            except AttributeError:
                                default_value = str(node.args.defaults[default_index])

                    parameters.append(ParameterInfo(name=param_name, type=type_annotation, default=default_value))

                # Handle keyword-only arguments
                if node.args.kwonlyargs:
                    kw_defaults = node.args.kw_defaults or []
                    for i, arg in enumerate(node.args.kwonlyargs):
                        param_name = arg.arg
                        type_annotation = None
                        default_value = None

                        # Extract type annotation if present
                        if arg.annotation:
                            try:
                                type_annotation = ast.unparse(arg.annotation)
                            except AttributeError:
                                type_annotation = str(arg.annotation)

                        # Extract default value if present
                        if i < len(kw_defaults) and kw_defaults[i] is not None:
                            default_node = kw_defaults[i]
                            if default_node is not None:
                                try:
                                    default_value = ast.unparse(default_node)
                                except AttributeError:
                                    default_value = str(default_node)

                        parameters.append(ParameterInfo(name=param_name, type=type_annotation, default=default_value))

                return parameters

        return []

    @staticmethod
    def parse_script(code_string: str, restricted: bool = True) -> ParsedScriptInfo:
        found_notte_operations: set[str] = set()

        class StatefulScriptValidator(ScriptValidator):
            @override
            def visit_Call(self, node: ast.Call) -> ast.AST:
                """Override to add custom call restrictions"""
                call_name = self._get_call_name(node)
                # Track notte operations
                if call_name and call_name in self.NOTTE_OPERATIONS:
                    found_notte_operations.add(call_name)
                return super().visit_Call(node)

        # 1. Parse the AST first to check for run function
        tree = ast.parse(code_string)

        # 2. Check if run function exists
        if not ScriptValidator._check_run_function_exists(tree):
            raise MissingRunFunctionError("Python script must contain a 'run' function")

        # 3. Extract run function parameters
        run_parameters = ScriptValidator._extract_run_function_parameters(tree)

        if not restricted:
            # For non-strict mode, use regular Python compilation
            code = compile(code_string, filename="<user_script.py>", mode="exec")
            return ParsedScriptInfo(code=code, variables=run_parameters)

        # 4. Compile with RestrictedPython validation (strict mode only)
        code: types.CodeType = compile_restricted(  # pyright: ignore [reportUnknownVariableType]
            code_string, filename="<user_script.py>", mode="exec", policy=StatefulScriptValidator
        )

        # 5. Validate that at least one notte operation is present (strict mode only)
        if restricted and not found_notte_operations:
            raise ValueError(
                f"Python script must contain at least one notte operation ({ScriptValidator.NOTTE_OPERATIONS})"
            )

        return ParsedScriptInfo(code=code, variables=run_parameters)  # pyright: ignore [reportUnknownArgumentType]


@final
class SecureScriptRunner:
    """Secure runner for notte scripts"""

    def __init__(self, notte_module: NotteModule):
        self.notte_module = notte_module

    def create_restricted_logger(self, level: str = "INFO"):
        """
        Create a restricted logger that's safe for user scripts
        """
        import sys

        from notte_core.common.logging import logger

        # Create a new logger instance to avoid conflicts
        user_logger = logger.bind(user_script=True)

        # Optional: Configure logger to only output to stdout/stderr
        # and prevent users from logging to files
        user_logger.remove()  # Remove default handler
        user_logger.add(  # pyright: ignore [reportUnusedCallResult]
            sys.stdout,
            level=level,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>user_script</cyan> | <level>{message}</level>",
            colorize=True,
        )
        return user_logger

    def _is_safe_attribute(self, attr_value: Any) -> bool:
        """
        Determine if an attribute is safe to expose
        """
        # Allow classes, functions, and basic data types
        safe_types = (
            type,  # Classes
            types.FunctionType,  # Regular functions
            types.MethodType,  # Methods
            types.BuiltinFunctionType,  # Built-in functions
            types.BuiltinMethodType,  # Built-in methods
            str,
            int,
            float,
            bool,  # Basic data types
            list,
            dict,
            tuple,
            set,  # Collections
            type(None),  # None
        )

        # Block dangerous types
        dangerous_types = (
            types.ModuleType,  # Modules could contain dangerous functions
            types.CodeType,  # Code objects
            types.FrameType,  # Frame objects
        )

        if isinstance(attr_value, dangerous_types):
            return False

        if isinstance(attr_value, safe_types):
            return True

        # Allow callable objects (like classes and functions)
        if callable(attr_value):
            return True

        # Be conservative - if we're not sure, don't allow it
        return False

    def create_restricted_notte(self):
        """
        Alternative approach: Use types.SimpleNamespace for a cleaner solution
        """
        import types

        restricted_notte = types.SimpleNamespace()

        # Copy all public attributes
        for attr_name in dir(self.notte_module):
            if not attr_name.startswith("_"):  # Only public attributes
                attr_value = getattr(self.notte_module, attr_name)
                if self._is_safe_attribute(attr_value):
                    setattr(restricted_notte, attr_name, attr_value)

        return restricted_notte

    def get_safe_globals(self) -> dict[str, Any]:
        """
        Create a safe global environment for script execution
        """
        # Start with RestrictedPython's safe globals (includes safe builtins)
        restricted_globals: dict[str, Any] = safe_globals.copy()

        # Add __import__ to __builtins__ so RestrictedPython can find it
        if "__builtins__" in restricted_globals:
            builtins_value = restricted_globals["__builtins__"]
            if isinstance(builtins_value, dict):
                builtins_value["__import__"] = self.safe_import
            else:
                # Convert __builtins__ module to dict and add __import__
                builtins_dict: dict[str, Any] = {}
                if hasattr(builtins_value, "__dict__"):
                    builtins_dict.update(builtins_value.__dict__)
                builtins_dict["__import__"] = self.safe_import
                restricted_globals["__builtins__"] = builtins_dict
        else:
            restricted_globals["__builtins__"] = {"__import__": self.safe_import}

        # Add our custom safe objects
        restricted_globals.update(
            {
                "notte": self.create_restricted_notte(),
                "logger": self.create_restricted_logger(),
                # Required guard functions for RestrictedPython
                "_getattr_": self.safe_getattr,
                "_getitem_": self.safe_getitem,
                "_getiter_": self.safe_getiter,
                "_write_": self.safe_write,
                # RestrictedPython requires these variables to be defined
                "__metaclass__": type,  # Required for RestrictedPython compiled code
                "_iter_unpack_sequence_": iter,  # Iterator unpacking guard
                "__name__": "__main__",  # Standard module name
                "__file__": "<user_script.py>",  # Standard filename
                # Import handling
                # Additional safe built-ins that might be useful
                "len": len,
                "str": str,
                "int": int,
                "float": float,
                "bool": bool,
                "list": list,
                "dict": dict,
                "tuple": tuple,
                "set": set,
                "min": min,
                "max": max,
                "sum": sum,
                "abs": abs,
                "round": round,
                "sorted": sorted,
                "enumerate": enumerate,
                "zip": zip,
                "range": range,
            }
        )

        return restricted_globals

    def safe_getattr(
        self, obj: Any, name: str, default: Any = None, getattr: Callable[[Any, str], Any] = getattr
    ) -> Any:
        """
        Safe attribute access guard
        """
        # Block access to dangerous attributes
        dangerous_attrs = {
            "__class__",
            "__bases__",
            "__subclasses__",
            "__mro__",
            "__globals__",
            "__code__",
            "__func__",
            "__self__",
            "__dict__",
            "__getattribute__",
            "__setattr__",
            "__delattr__",
        }

        if name in dangerous_attrs:
            raise AttributeError(f"Access to attribute '{name}' is not allowed")

        # Block access to private attributes
        if name.startswith("_"):
            raise AttributeError(f"Access to private attribute '{name}' is not allowed")

        return getattr(obj, name, default)  # pyright: ignore [reportUnknownVariableType, reportCallIssue]

    def safe_getitem(self, obj: Any, key: Any):
        """
        Safe item access guard
        """
        return obj[key]

    def safe_getiter(self, obj: Any):
        """
        Safe iterator guard
        """
        return iter(obj)

    def safe_write(self, obj: Any):
        """
        Safe write guard - controls what can be assigned to
        """
        return obj

    def safe_import(self, name: str, *args: Any, **kwargs: Any):
        """
        Safe import guard - only allow whitelisted modules
        """
        ScriptValidator.check_valid_import(name)

        return __import__(name, *args, **kwargs)

    def custom_import_guard(self, name: str, *args: Any, **kwargs: Any):
        """
        Custom import guard - block all imports except whitelisted ones
        DEPRECATED: Use safe_import instead
        """
        allowed_imports = {
            # You can add specific modules here if needed
            # 'math', 'datetime', 'json'
        }

        if name not in allowed_imports:
            raise ImportError(f"Import of '{name}' is not allowed")

        return __import__(name, *args, **kwargs)

    def _validate_variables(self, run_parameters: list[ParameterInfo], variables: dict[str, Any] | None) -> None:
        """
        Validate that the provided variables match the run function's expected parameters

        Args:
            run_parameters: List of parameters expected by the run function
            variables: Variables to be passed to the run function

        Raises:
            ValueError: If validation fails
        """
        variables = variables or {}

        # Collect required parameters (those without defaults)
        required_params = {param.name for param in run_parameters if param.default is None}
        provided_params = set(variables.keys())
        all_params = {param.name for param in run_parameters}

        # Check for missing required parameters
        missing_required = required_params - provided_params
        if missing_required:
            raise ValueError(f"Missing required parameters for run function: {sorted(missing_required)}")

        # Check for unexpected parameters
        unexpected_params = provided_params - all_params
        if unexpected_params:
            raise ValueError(
                f"Unexpected variable names for run function: {sorted(unexpected_params)} (expected variable names: {sorted(all_params)})"
            )

        # Optional: Log parameter information for debugging
        if hasattr(self, "logger"):
            param_info: list[str] = []
            for param in run_parameters:
                type_str = f": {param.type}" if param.type else ""
                default_str = f" = {param.default}" if param.default is not None else " (required)"
                param_info.append(f"{param.name}{type_str}{default_str}")

            if param_info:
                self.create_restricted_logger().debug(f"Run function parameters: {', '.join(param_info)}")

    def run_script(self, code_string: str, variables: dict[str, Any] | None = None, restricted: bool = False) -> Any:
        """
        Run a user script with optional RestrictedPython validation

        Args:
            code_string: The Python script to execute
            variables: Variables to pass to the run function
            restricted: If True, use RestrictedPython for safety (default: False)
                   If False, use regular Python execution (full access)
        """
        # Parse the script to get code and parameter information
        parsed_info = ScriptValidator.parse_script(code_string, restricted=restricted)

        # Validate variables against run function parameters
        self._validate_variables(parsed_info.variables, variables)

        if restricted:
            # Use RestrictedPython for strict mode
            execution_globals = self.get_safe_globals()
            result: Mapping[str, object] = {}

            try:
                exec(parsed_info.code, execution_globals, result)

                # Call the run function if it exists
                run_ft = result.get("run")
                if run_ft is None or not callable(run_ft):
                    raise MissingRunFunctionError("Script must contain a 'run' function")
                if callable(run_ft):
                    return run_ft(**variables) if variables else run_ft()

                return result

            except Exception:
                raise RuntimeError(f"Python script execution failed in restricted mode: {traceback.format_exc()}")
        else:
            # Use regular Python execution for non-strict mode
            # Create execution namespace with notte module and logger
            execution_globals = {
                "notte": self.notte_module,
                "logger": self.create_restricted_logger(),
            }

            try:
                # Execute the script in regular Python
                exec(parsed_info.code, execution_globals)

                # Call the run function
                run_ft = execution_globals.get("run")
                if run_ft is None or not callable(run_ft):
                    raise MissingRunFunctionError("Python script must contain a 'run' function")
                if callable(run_ft):
                    return run_ft(**variables) if variables else run_ft()  # pyright: ignore [reportUnknownVariableType]

                return execution_globals

            except Exception:
                raise RuntimeError(f"Script execution failed in unrestricted mode: {traceback.format_exc()}")
