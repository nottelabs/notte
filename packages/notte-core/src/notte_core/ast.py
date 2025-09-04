import ast
import traceback
import types
from collections.abc import Mapping
from typing import Any, Callable, ClassVar, Literal, Protocol, final

from RestrictedPython import compile_restricted, safe_globals  # type: ignore [reportMissingTypeStubs]
from RestrictedPython.transformer import RestrictingNodeTransformer  # type: ignore [reportMissingTypeStubs]
from typing_extensions import override


class MissingRunFunctionError(Exception):
    """Raised when a script does not contain a required 'run' function"""

    pass


class NotteModule(Protocol):
    Chapter: type
    Agent: type
    Session: type


class ScriptValidator(RestrictingNodeTransformer):
    """Validates that the AST only contains allowed operations"""

    # Notte-specific operations that must be present in valid scripts
    NOTTE_OPERATIONS: ClassVar[set[str]] = {
        "session.execute",
        "session.observe",
        "session.storage",
        "session.scrape",
        "session.storage.instructions",  # Allow access to storage instructions
        "notte.Session",
        "notte.SessionScript",
        "notte.AgentFallback",
        "notte.Agent",
        "notte.Agent.run",
        "notte.Agent.arun",
    }

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
        # Safe standard library modules - data processing and utilities
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
    }

    FORBIDDEN_NODES: set[type[ast.AST]] = {
        # Dangerous operations - removed ast.Import and ast.ImportFrom to handle separately
        # ast.FunctionDef,  # Allow function definitions but validate them separately
        ast.AsyncFunctionDef,
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
        ast.Await,
        ast.Delete,
        # ast.AugAssign,
        ast.AsyncFunctionDef,
    }

    FORBIDDEN_CALLS: set[str] = {
        "open",
        "input",
        "print",  # print might be OK depending on your needs
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
        "hash",
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
    def parse_script(code_string: str, restricted: bool = True) -> types.CodeType:
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

        if not restricted:
            # For non-strict mode, use regular Python compilation
            return compile(code_string, filename="<user_script.py>", mode="exec")

        # 3. Compile with RestrictedPython validation (strict mode only)
        code = compile_restricted(code_string, filename="<user_script.py>", mode="exec", policy=StatefulScriptValidator)  # pyright: ignore [reportUnknownVariableType]

        # 4. Validate that at least one notte operation is present (strict mode only)
        if restricted and not found_notte_operations:
            raise ValueError(
                f"Python script must contain at least one notte operation ({ScriptValidator.NOTTE_OPERATIONS})"
            )
        return code  # pyright: ignore [reportUnknownVariableType]


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

        from loguru import logger

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
            if isinstance(restricted_globals["__builtins__"], dict):
                restricted_globals["__builtins__"]["__import__"] = self.safe_import
            else:
                # Convert __builtins__ module to dict and add __import__
                builtins_dict = {}
                if hasattr(restricted_globals["__builtins__"], "__dict__"):
                    builtins_dict.update(restricted_globals["__builtins__"].__dict__)  # pyright: ignore [reportUnknownMemberType]
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

    def run_script(self, code_string: str, variables: dict[str, Any] | None = None, restricted: bool = False) -> Any:
        """
        Run a user script with optional RestrictedPython validation

        Args:
            code_string: The Python script to execute
            variables: Variables to pass to the run function
            restricted: If True, use RestrictedPython for safety (default: False)
                   If False, use regular Python execution (full access)
        """

        if restricted:
            # Use RestrictedPython for strict mode
            code = ScriptValidator.parse_script(code_string, restricted=restricted)
            execution_globals = self.get_safe_globals()
            result: Mapping[str, object] = {}

            try:
                exec(code, execution_globals, result)

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
            # First check that run function exists
            tree = ast.parse(code_string)
            if not self._check_run_function_exists_static(tree):
                raise MissingRunFunctionError("Python script must contain a 'run' function")

            # Create execution namespace with notte module and logger
            execution_globals = {
                "notte": self.notte_module,
                "logger": self.create_restricted_logger(),
            }

            try:
                # Execute the script in regular Python
                exec(code_string, execution_globals)

                # Call the run function
                run_ft = execution_globals.get("run")
                if run_ft is None or not callable(run_ft):
                    raise MissingRunFunctionError("Python script must contain a 'run' function")
                if callable(run_ft):
                    return run_ft(**variables) if variables else run_ft()  # pyright: ignore [reportUnknownVariableType]

                return execution_globals

            except Exception:
                raise RuntimeError(f"Script execution failed in unrestricted mode: {traceback.format_exc()}")

    def _check_run_function_exists_static(self, tree: ast.Module) -> bool:
        """Check if the AST contains a function named 'run'"""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "run":
                return True
        return False
