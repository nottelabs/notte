from __future__ import annotations

from typing import TYPE_CHECKING, Unpack, overload

from typing_extensions import override

from notte_sdk.endpoints.workflows import RemoteWorkflow
from notte_sdk.types import CreateFunctionRequestDict, CreateFunctionRunResponse

if TYPE_CHECKING:
    from notte_sdk.client import NotteClient


class NotteFunction(RemoteWorkflow):
    """
    Notte function that can be run on the cloud or locally.

    Functions are saved in the notte console for easy access and versioning for users.
    This is a wrapper around RemoteWorkflow that uses function_id terminology.
    """

    @overload
    def __init__(
        self, /, function_id: str, *, decryption_key: str | None = None, _client: NotteClient | None = None
    ) -> None: ...

    @overload
    def __init__(self, *, _client: NotteClient | None = None, **data: Unpack[CreateFunctionRequestDict]) -> None: ...

    def __init__(  # pyright: ignore[reportInconsistentOverload]
        self,
        function_id: str | None = None,
        *,
        decryption_key: str | None = None,
        _client: NotteClient | None = None,
        **data: Unpack[CreateFunctionRequestDict],
    ) -> None:
        # Pass function_id to parent RemoteWorkflow constructor
        if function_id is not None:
            # Call with positional argument to match first overload
            super().__init__(function_id, decryption_key=decryption_key, _client=_client)  # pyright: ignore[reportDeprecated]
        else:
            # Call with keyword arguments to match second overload
            super().__init__(_client=_client, **data)  # pyright: ignore[reportDeprecated]

    def create_run(self, local: bool = False) -> CreateFunctionRunResponse:
        """
        Create a run record without starting execution.

        Returns the run ID before execution begins. Pass it explicitly to
        `run(function_run_id=...)` to execute this run; `run()` without an ID
        creates a new run. Use the same `local` value when creating and running.

        ```python
        function = notte.Function("<your-function-id>")
        created = function.create_run()
        result = function.run(function_run_id=created.function_run_id, url="https://example.com")
        ```

        `run()` still waits for completion. Creating a run does not launch a
        background job or change which run `run()` uses by default.
        """
        return self.client.create_run(self._function_id, local=local)

    @override
    def fork(self) -> "NotteFunction":
        """
        Fork a shared function into your own private function.

        ```python
        function = notte.Function("<user-shared-function-id>")
        forked_function = function.fork()
        forked_function.run()
        ```

        The forked function is only accessible to you and you can update it as you want.
        """
        fork_response = self.client.fork(function_id=self._function_id)
        return NotteFunction(function_id=fork_response.function_id, _client=self.root_client)
