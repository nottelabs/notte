import ast
import types
from typing import Any, Callable, ClassVar, Protocol, final

from RestrictedPython import compile_restricted, safe_globals  # type: ignore [reportMissingTypeStubs]
from RestrictedPython.transformer import RestrictingNodeTransformer  # type: ignore [reportMissingTypeStubs]
from typing_extensions import override


class NotteModule(Protocol):
    Script: type
    Chapter: type
    Agent: type


class ScriptValidator(RestrictingNodeTransformer):
    """Validates that the AST only contains allowed operations"""

    # Notte-specific operations that must be present in valid scripts
    NOTTE_OPERATIONS: ClassVar[set[str]] = {
        "session.execute",
        "session.observe",
        "session.storage",
        "session.scrape",
        "session.storage.instructions",  # Allow access to storage instructions
        "notte.Script",
        "notte.Chapter",
        "notte.Agent",
        "notte.Agent.run",
        "notte.Agent.arun",
    }

    FORBIDDEN_NODES: set[type[ast.AST]] = {
        # Dangerous operations
        ast.Import,
        ast.ImportFrom,
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
        ast.Global,
        ast.Nonlocal,
        # Allow try/except blocks to be used in scripts
        # ast.Try,
        # ast.ExceptHandler,
        ast.TryStar,
        # Advanced features that could be misused
        ast.Lambda,
        ast.GeneratorExp,
        ast.Yield,
        ast.YieldFrom,
        ast.Await,
        ast.Delete,
        ast.AugAssign,
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

    @override
    def visit(self, node: ast.AST) -> ast.AST:
        """Override to add custom node restrictions"""
        if type(node) in self.FORBIDDEN_NODES:
            raise SyntaxError(f"Forbidden AST node in Notte script: {type(node).__name__}")
        return super().visit(node)

    @staticmethod
    def parse_script(code_string: str) -> ast.Module:
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

        # 1. Parse and validate AST
        code = compile_restricted(code_string, filename="<user_script>", mode="exec", policy=StatefulScriptValidator)  # pyright: ignore [reportUnknownVariableType]
        # 2. Validate that at least one notte operation is present
        if not found_notte_operations:
            raise ValueError(f"Script must contain at least one notte operation ({ScriptValidator.NOTTE_OPERATIONS})")
        return code  # pyright: ignore [reportUnknownVariableType]


@final
class SecureScriptRunner:
    """Secure runner for notte scripts"""

    def __init__(self, notte_module: NotteModule):
        self.validator: ScriptValidator = ScriptValidator()
        self.notte_module = notte_module
        self.execution_timeout = 300  # 5 minutes max

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
        # Block access to private attributes
        if name.startswith("_"):
            raise AttributeError(f"Access to private attribute '{name}' is not allowed")

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

    def custom_import_guard(self, name: str, *args: Any, **kwargs: Any):
        """
        Custom import guard - block all imports except whitelisted ones
        """
        allowed_imports = {
            # You can add specific modules here if needed
            # 'math', 'datetime', 'json'
        }

        if name not in allowed_imports:
            raise ImportError(f"Import of '{name}' is not allowed")

        return __import__(name, *args, **kwargs)

    def run_script(self, code_string: str) -> Any:
        """
        Safely run a user script using RestrictedPython
        """
        # Compile the code with RestrictedPython
        code = self.validator.parse_script(code_string)

        # Create the restricted execution environment
        restricted_globals = self.get_safe_globals()

        # Execute the compiled code
        try:
            # Note: In production, you'd want to add proper timeout handling
            # using signal.alarm(), threading.Timer, or process-based execution
            result = {}
            exec(code, restricted_globals, result)  # pyright: ignore
            return result  # pyright: ignore [reportUnknownVariableType]

        except Exception as e:
            raise RuntimeError(f"Script execution failed: {e}")
