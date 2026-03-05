#!/usr/bin/env python3
"""
Generate synchronous code from async implementations.

This script transforms async code in _async/ to sync code in _sync/.
Based on httpcore's unasync approach.

Usage:
    python scripts/unasync.py
"""

import re
import shutil
import subprocess
from pathlib import Path

# Source and destination directories
SRC_DIR = Path(__file__).parent.parent / "src" / "notte_sdk" / "_async"
DST_DIR = Path(__file__).parent.parent / "src" / "notte_sdk" / "_sync"

# Mapping of async names to sync names
REPLACEMENTS = [
    # Module imports
    ("from notte_sdk._async.", "from notte_sdk._sync."),
    ("notte_sdk._async.", "notte_sdk._sync."),
    # Class name replacements
    ("AsyncNotteClient", "NotteClient"),
    ("AsyncHTTPClient", "HTTPClient"),
    ("AsyncBaseClient", "BaseClient"),
    ("AsyncSessionsClient", "SessionsClient"),
    ("AsyncRemoteSession", "RemoteSession"),
    ("AsyncPageClient", "PageClient"),
    ("AsyncAgentsClient", "AgentsClient"),
    ("AsyncVaultsClient", "VaultsClient"),
    ("AsyncNotteVault", "NotteVault"),
    ("AsyncPersonasClient", "PersonasClient"),
    ("AsyncNottePersona", "NottePersona"),
    ("AsyncBasePersona", "BasePersona"),
    ("AsyncProfilesClient", "ProfilesClient"),
    ("AsyncFileStorageClient", "FileStorageClient"),
    ("AsyncRemoteFileStorage", "RemoteFileStorage"),
    ("AsyncWorkflowsClient", "WorkflowsClient"),
    # Resource classes
    ("AsyncRemoteAgent", "RemoteAgent"),
    ("AsyncBatchRemoteAgent", "BatchRemoteAgent"),
    ("AsyncRemoteWorkflow", "RemoteWorkflow"),
    ("AsyncNotteFunction", "NotteFunction"),
    ("AsyncRemoteAgentFallback", "RemoteAgentFallback"),
    ("AsyncAgentWorkflow", "AgentWorkflow"),
    # Resource base class
    ("AsyncResource", "SyncResource"),
    ("from notte_core.common.resource import AsyncResource", "from notte_core.common.resource import SyncResource"),
    # Async context managers
    ("async with", "with"),
    ("__aenter__", "__enter__"),
    ("__aexit__", "__exit__"),
    # Async iterator
    ("async for", "for"),
    ("__aiter__", "__iter__"),
    ("__anext__", "__next__"),
    # httpx async client
    ("httpx.AsyncClient", "httpx.Client"),
    # Playwright async
    ("playwright.async_api", "playwright.sync_api"),
    ("_async_playwright_available", "_playwright_available"),
    ("_async_playwright_context", "_playwright_context"),
    ("_async_playwright_browser", "_playwright_browser"),
    ("_async_playwright_page", "_playwright_page"),
    ("_async_playwright", "_sync_playwright"),
    ("async_playwright", "sync_playwright"),
    ("PlaywrightAsync", "PlaywrightSync"),
    ("BrowserAsync", "BrowserSync"),
    ("PageAsync", "PageSync"),
    # Async method names that should become sync
    ("async def astart", "def start"),
    ("async def astop", "def stop"),
    ("async def aclose", "def close"),
    ("async def adelete", "def delete"),
    ("async def aemails", "def emails"),
    ("async def asms", "def sms"),
    ("async def adownload", "def download"),
    ("async def aupload", "def upload"),
    ("await self.astart", "self.start"),
    ("await self.astop", "self.stop"),
    ("await self.aclose", "self.close"),
    # Also handle vault.astart etc. (when called on other objects)
    (".astart()", ".start()"),
    (".astop()", ".stop()"),
    (".aclose()", ".close()"),
    ("self._http.aclose", "self._http.close"),
    ("self._client.aclose", "self._client.close"),
    ("await self.adelete", "self.delete"),
    ("await self.aemails", "self.emails"),
    ("await self.asms", "self.sms"),
    ("await self._aget_vault", "self._get_vault"),
    ("async def _aget_vault", "def _get_vault"),
    # Property async
    ("@property\n    async def apage", "@property\n    def page"),
    ("await session.apage", "session.page"),
    ("await self.apage", "self.page"),
    # Sleep
    ("await asyncio.sleep", "time.sleep"),
    ("asyncio.sleep", "time.sleep"),
    # httpx streaming
    ("aiter_bytes", "iter_bytes"),
    # Remove Coroutine from imports (only used in async code)
    ("from collections.abc import Callable, Coroutine, Sequence", "from collections.abc import Callable, Sequence"),
]

# Regex patterns for more complex transformations
REGEX_REPLACEMENTS = [
    # async def -> def
    (r"async def (\w+)", r"def \1"),
    # await expression
    (r"await\s+", ""),
    # asyncio.Queue -> queue.Queue
    (r"asyncio\.Queue\[([^\]]+)\]", r"queue.Queue[\1]"),
    (r"asyncio\.Queue\(\)", r"queue.Queue()"),
]

# Methods that must stay async to match abstract methods from notte_core
# Even in sync version, these need async def to satisfy the override contract
# Note: These are applied globally, so we need file-specific fixes for methods
# that have the same name in non-override contexts (like client methods)
PRESERVE_ASYNC_METHODS = [
    # BaseVault abstract methods
    "_add_credentials",
    "_get_credentials_impl",
    "delete_credentials_async",
    "set_credit_card_async",
    "get_credit_card_async",
    "list_credentials_async",
    "delete_credit_card_async",
    # BaseStorage abstract methods (get_file, set_file are unique enough)
    "get_file",
    "set_file",
    # NOTE: list_uploaded_files and list_downloaded_files are handled
    # specifically in fix_files_sync() because the client also has these methods
]


def transform_content(content: str) -> str:
    """Transform async code to sync code."""
    # Apply simple string replacements
    for old, new in REPLACEMENTS:
        content = content.replace(old, new)

    # Apply regex replacements
    for pattern, replacement in REGEX_REPLACEMENTS:
        content = re.sub(pattern, replacement, content)

    # Restore async def for methods that must stay async to match BaseVault overrides
    for method in PRESERVE_ASYNC_METHODS:
        content = re.sub(rf"\bdef ({method})\b", r"async def \1", content)

    # Add time import if we converted asyncio.sleep to time.sleep
    if "time.sleep" in content and "import time" not in content:
        # Find the import section and add time import
        lines: list[str] = content.split("\n")
        new_lines: list[str] = []
        import_added = False
        for line in lines:
            new_lines.append(line)
            if not import_added and line.startswith("import ") or line.startswith("from "):
                # Check if next line is also import
                continue
            if not import_added and (
                line.strip() == ""
                and len(new_lines) > 1
                and (new_lines[-2].startswith("import ") or new_lines[-2].startswith("from "))
            ):
                new_lines.insert(-1, "import time")
                import_added = True
        content = "\n".join(new_lines)

    # Add queue import if we converted asyncio.Queue to queue.Queue
    if "queue.Queue" in content and "import queue" not in content:
        lines = content.split("\n")
        new_lines = []
        import_added = False
        for line in lines:
            new_lines.append(line)
            if not import_added and line.startswith("import ") or line.startswith("from "):
                continue
            if not import_added and (
                line.strip() == ""
                and len(new_lines) > 1
                and (new_lines[-2].startswith("import ") or new_lines[-2].startswith("from "))
            ):
                new_lines.insert(-1, "import queue")
                import_added = True
        content = "\n".join(new_lines)

    return content


def fix_files_sync(content: str) -> str:
    """Fix RemoteFileStorage to keep list_* methods async for BaseStorage override.

    The list_uploaded_files and list_downloaded_files methods exist in both:
    - FileStorageClient (should be sync)
    - RemoteFileStorage (should stay async for BaseStorage override)

    We selectively restore async for just the RemoteFileStorage methods.
    """
    # Find and fix the RemoteFileStorage.list_uploaded_files method
    content = content.replace(
        '''    @override
    def list_uploaded_files(self) -> list[FileInfo]:
        """List uploaded files in storage."""
        return self.client.list_uploaded_files()''',
        '''    @override
    async def list_uploaded_files(self) -> list[FileInfo]:
        """List uploaded files in storage."""
        return self.client.list_uploaded_files()''',
    )

    # Find and fix the RemoteFileStorage.list_downloaded_files method
    content = content.replace(
        '''    @override
    def list_downloaded_files(self) -> list[FileInfo]:
        """List downloaded files in storage."""
        return self.client.list_downloaded_files(session_id=self.session_id)''',
        '''    @override
    async def list_downloaded_files(self) -> list[FileInfo]:
        """List downloaded files in storage."""
        return self.client.list_downloaded_files(session_id=self.session_id)''',
    )

    return content


def fix_vault_sync(content: str) -> str:
    """Remove async method overrides from sync NotteVault.

    The async version overrides BaseVault's sync methods to be async.
    The sync version should use BaseVault's sync implementations instead.
    """
    # Remove the block of async override methods
    override_block = '''
    # Override sync methods from BaseVault to be async (avoid asyncio.run in async context)
    def add_credentials(self, url: str, **kwargs: Unpack[CredentialsDict]) -> None:  # type: ignore[override]
        """Store credentials for a given URL (async version)."""
        return self.add_credentials_async(url, **kwargs)

    def set_credit_card(self, **kwargs: Unpack[CreditCardDict]) -> None:  # type: ignore[override]
        """Store credit card information (async version)."""
        return self.set_credit_card_async(**kwargs)

    def get_credit_card(self) -> CreditCardDict:  # type: ignore[override]
        """Retrieve credit card information (async version)."""
        return self.get_credit_card_async()

    def delete_credit_card(self) -> None:  # type: ignore[override]
        """Remove saved credit card information (async version)."""
        return self.delete_credit_card_async()

    def delete_credentials(self, url: str) -> None:  # type: ignore[override]
        """Remove credentials for a given URL (async version)."""
        return self.delete_credentials_async(url)

    def list_credentials(self) -> list[Credential]:  # type: ignore[override]
        """List urls for which we hold credentials (async version)."""
        return self.list_credentials_async()

    def has_credential(self, url: str) -> bool:  # type: ignore[override]
        """Check whether we hold a credential for a given website (async version)."""
        return self.has_credential_async(url)

    def add_credentials_from_env(self, url: str) -> None:  # type: ignore[override]
        """Add credentials from environment variables for a given URL (async version)."""
        return self.add_credentials_from_env_async(url)

    def get_credentials(self, url: str) -> CredentialsDict | None:  # type: ignore[override]
        """Get credentials for a given URL (async version)."""
        return self.get_credentials_async(url)'''

    return content.replace(override_block, "")


def fix_batch_agent_sync(content: str) -> str:
    """Fix BatchRemoteAgent.run_batch to use concurrent.futures for sync execution."""
    # Fix the overloads to use Callable[[], T] instead of Callable[[], Coroutine[...]]
    content = content.replace(
        "task_creator: Callable[[], Coroutine[Any, Any, AgentStatusResponse]],",
        "task_creator: Callable[[], AgentStatusResponse],",
    )

    # Replace the asyncio-based parallel execution with concurrent.futures
    # This matches the already-transformed code (await removed, async def -> def)
    old_run_batch = '''    @staticmethod
    def run_batch(
        task_creator: Callable[[], AgentStatusResponse],
        n_jobs: int = 2,
        strategy: Literal["all_finished", "first_success"] = "first_success",
    ) -> AgentStatusResponse | list[AgentStatusResponse]:
        """Internal method to run multiple agents in batch mode."""
        tasks: list[asyncio.Task[AgentStatusResponse]] = []
        results: list[AgentStatusResponse] = []

        for _ in range(n_jobs):
            task = asyncio.create_task(task_creator())
            tasks.append(task)

        exception = None
        for completed_task in asyncio.as_completed(tasks):
            try:
                result = completed_task

                if result.success and strategy == "first_success":
                    for task in tasks:
                        if not task.done():
                            _ = task.cancel()
                    return result
                else:
                    results.append(result)
            except Exception as e:
                exception = e
                logger.error(
                    f"Batch task failed: {exception.__class__.__qualname__} {exception} {traceback.format_exc()}"
                )
                continue

        if strategy == "first_success":
            if len(results) > 0:
                return results[0]
            else:
                if exception is None:
                    exception = ValueError(
                        "Every run of the task failed, yet no exception found: this should not happen"
                    )
                raise exception

        return results'''

    new_run_batch = '''    @staticmethod
    def run_batch(
        task_creator: Callable[[], AgentStatusResponse],
        n_jobs: int = 2,
        strategy: Literal["all_finished", "first_success"] = "first_success",
    ) -> AgentStatusResponse | list[AgentStatusResponse]:
        """Internal method to run multiple agents in batch mode (sync: uses ThreadPoolExecutor)."""
        from concurrent.futures import ThreadPoolExecutor, as_completed, Future

        futures: list[Future[AgentStatusResponse]] = []
        results: list[AgentStatusResponse] = []

        with ThreadPoolExecutor(max_workers=n_jobs) as executor:
            for _ in range(n_jobs):
                future = executor.submit(task_creator)
                futures.append(future)

            exception = None
            for completed_future in as_completed(futures):
                try:
                    result = completed_future.result()

                    if result.success and strategy == "first_success":
                        # Cancel remaining futures (best effort)
                        for future in futures:
                            future.cancel()
                        return result
                    else:
                        results.append(result)
                except Exception as e:
                    exception = e
                    logger.error(
                        f"Batch task failed: {exception.__class__.__qualname__} {exception} {traceback.format_exc()}"
                    )
                    continue

        if strategy == "first_success":
            if len(results) > 0:
                return results[0]
            else:
                if exception is None:
                    exception = ValueError(
                        "Every run of the task failed, yet no exception found: this should not happen"
                    )
                raise exception

        return results'''

    return content.replace(old_run_batch, new_run_batch)


def fix_agents_websocket_sync(content: str) -> str:
    """Fix websocket code in agents.py - websockets library is async-only.

    The _watch_logs_ws method uses websockets.asyncio.client.connect which is
    async-only. For sync code, we add pyright ignore directives.
    """
    # Add pyright ignore for the websocket connect line
    content = content.replace(
        "with client.connect(  # pyright: ignore[reportPossiblyUnboundVariable]",
        "with client.connect(  # pyright: ignore[reportPossiblyUnboundVariable, reportGeneralTypeIssues]",
    )
    return content


def transform_file(src_path: Path, dst_path: Path) -> None:
    """Transform a single file from async to sync."""
    content = src_path.read_text()
    transformed = transform_content(content)

    # Apply file-specific fixes
    if src_path.name == "agents.py":
        transformed = fix_batch_agent_sync(transformed)
        transformed = fix_agents_websocket_sync(transformed)
    if src_path.name == "vaults.py":
        transformed = fix_vault_sync(transformed)
    if src_path.name == "files.py":
        transformed = fix_files_sync(transformed)
    if src_path.name == "personas.py":
        # _add_credentials is kept async for BaseVault override, so wrap call in asyncio.run
        transformed = transformed.replace("vault._add_credentials(url, ", "asyncio.run(vault._add_credentials(url, ")
        transformed = transformed.replace(
            '{"email": self.info.email, "password": password})', '{"email": self.info.email, "password": password}))'
        )
        # Ensure asyncio is imported (after __future__ imports)
        if "asyncio.run(" in transformed and "import asyncio" not in transformed:
            # Insert after __future__ imports
            if "from __future__ import" in transformed:
                transformed = transformed.replace(
                    "from __future__ import annotations\n", "from __future__ import annotations\n\nimport asyncio\n"
                )
            else:
                transformed = "import asyncio\n" + transformed

    # Add header comment
    if not transformed.startswith('"""Sync'):
        # Find first non-docstring line to insert after any module docstring
        if transformed.startswith('"""'):
            # Find end of docstring
            end = transformed.find('"""', 3)
            if end != -1:
                # Insert after docstring
                transformed = (
                    transformed[: end + 3]
                    + "\n# Auto-generated from _async/ - DO NOT EDIT DIRECTLY\n"
                    + transformed[end + 3 :]
                )
        else:
            transformed = "# Auto-generated from _async/ - DO NOT EDIT DIRECTLY\n" + transformed

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    _ = dst_path.write_text(transformed)
    print(f"Generated: {dst_path}")


def main() -> None:
    """Generate sync code from async code."""
    print(f"Source directory: {SRC_DIR}")
    print(f"Destination directory: {DST_DIR}")

    if not SRC_DIR.exists():
        print(f"Error: Source directory {SRC_DIR} does not exist")
        return

    # Clear destination directory
    if DST_DIR.exists():
        shutil.rmtree(DST_DIR)
    DST_DIR.mkdir(parents=True)

    # Process each Python file
    for src_file in SRC_DIR.glob("*.py"):
        dst_file = DST_DIR / src_file.name
        transform_file(src_file, dst_file)

    print(f"\nGenerated {len(list(DST_DIR.glob('*.py')))} files in {DST_DIR}")

    # Run ruff to fix import sorting and remove unused imports
    print("\nRunning ruff to fix imports...")
    try:
        result = subprocess.run(
            ["ruff", "check", "--fix", "--select", "I,F401", str(DST_DIR)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 and result.stderr:
            print(f"ruff warnings: {result.stderr}")
    except FileNotFoundError:
        print("Warning: ruff not found, skipping import sorting")


if __name__ == "__main__":
    main()
