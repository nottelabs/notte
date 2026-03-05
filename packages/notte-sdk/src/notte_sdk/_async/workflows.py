"""Async workflows endpoint client for the Notte SDK."""

from __future__ import annotations

import json
import warnings
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar, Unpack, overload

import httpx
from notte_core.ast import SecureScriptRunner
from notte_core.common.logging import logger
from notte_core.common.telemetry import track_usage
from notte_core.utils.encryption import Encryption
from notte_core.utils.webp_replay import MP4Replay
from typing_extensions import deprecated, final, override

from notte_sdk._async.base import AsyncBaseClient, NotteEndpoint
from notte_sdk._async.http import AsyncHTTPClient
from notte_sdk.types import (
    CreateFunctionRequest,
    CreateFunctionRequestDict,
    CreateFunctionRunRequest,
    CreateFunctionRunResponse,
    DeleteFunctionResponse,
    ForkFunctionRequest,
    FunctionRunResponse,
    FunctionRunUpdateRequest,
    FunctionRunUpdateRequestDict,
    GetFunctionRequest,
    GetFunctionRequestDict,
    GetFunctionResponse,
    GetFunctionRunResponse,
    GetFunctionWithLinkResponse,
    ListFunctionRunsRequest,
    ListFunctionRunsRequestDict,
    ListFunctionRunsResponse,
    ListFunctionsRequest,
    ListFunctionsRequestDict,
    ListFunctionsResponse,
    RunFunctionRequest,
    RunFunctionRequestDict,
    StartFunctionRunRequest,
    UpdateFunctionRequest,
    UpdateFunctionRequestDict,
    UpdateFunctionRunResponse,
)
from notte_sdk.utils import LogCapture

if TYPE_CHECKING:
    from notte_sdk._async.client import AsyncNotteClient


@final
class AsyncWorkflowsClient(AsyncBaseClient):
    """Async client for the Notte Workflows API."""

    # Workflow endpoints
    CREATE_WORKFLOW = ""
    FORK_WORKFLOW = "{function_id}/fork"
    UPDATE_WORKFLOW = "{function_id}?restricted={restricted}"
    GET_WORKFLOW = "{function_id}"
    DELETE_WORKFLOW = "{function_id}"
    LIST_WORKFLOWS = ""

    # Run endpoints
    CREATE_WORKFLOW_RUN = "{function_id}/runs/create"
    START_WORKFLOW_RUN_WITHOUT_RUN_ID = "{function_id}/runs/start"
    STOP_WORKFLOW_RUN = "{function_id}/runs/{run_id}"
    START_WORKFLOW_RUN = "{function_id}/runs/{run_id}"
    GET_WORKFLOW_RUN = "{function_id}/runs/{run_id}"
    LIST_WORKFLOW_RUNS = "{function_id}/runs/"
    UPDATE_WORKFLOW_RUN = "{function_id}/runs/{run_id}"
    RUN_WORKFLOW_ENDPOINT = "{function_id}/runs/{run_id}"

    WORKFLOW_RUN_TIMEOUT: ClassVar[int] = 60 * 5  # 5 minutes

    def __init__(
        self,
        root_client: "AsyncNotteClient",
        http_client: AsyncHTTPClient,
        server_url: str,
        api_key: str,
        verbose: bool = False,
    ):
        """Initialize AsyncWorkflowsClient."""
        super().__init__(
            root_client=root_client,
            base_endpoint_path="workflows",
            http_client=http_client,
            server_url=server_url,
            api_key=api_key,
            verbose=verbose,
        )

    @staticmethod
    def _create_workflow_endpoint() -> NotteEndpoint[GetFunctionResponse]:
        return NotteEndpoint(
            path=AsyncWorkflowsClient.CREATE_WORKFLOW,
            response=GetFunctionResponse,
            method="POST",
        )

    @staticmethod
    def _update_workflow_endpoint(function_id: str, restricted: bool = True) -> NotteEndpoint[GetFunctionResponse]:
        return NotteEndpoint(
            path=AsyncWorkflowsClient.UPDATE_WORKFLOW.format(function_id=function_id, restricted=restricted),
            response=GetFunctionResponse,
            method="POST",
        )

    @staticmethod
    def _get_workflow_endpoint(function_id: str) -> NotteEndpoint[GetFunctionWithLinkResponse]:
        return NotteEndpoint(
            path=AsyncWorkflowsClient.GET_WORKFLOW.format(function_id=function_id),
            response=GetFunctionWithLinkResponse,
            method="GET",
        )

    @staticmethod
    def _delete_workflow_endpoint(function_id: str) -> NotteEndpoint[DeleteFunctionResponse]:
        return NotteEndpoint(
            path=AsyncWorkflowsClient.DELETE_WORKFLOW.format(function_id=function_id),
            response=DeleteFunctionResponse,
            method="DELETE",
        )

    @staticmethod
    def _create_workflow_run_endpoint(function_id: str) -> NotteEndpoint[CreateFunctionRunResponse]:
        return NotteEndpoint(
            path=AsyncWorkflowsClient.CREATE_WORKFLOW_RUN.format(function_id=function_id),
            response=CreateFunctionRunResponse,
            method="POST",
        )

    @staticmethod
    def _fork_workflow_endpoint(function_id: str) -> NotteEndpoint[GetFunctionResponse]:
        return NotteEndpoint(
            path=AsyncWorkflowsClient.FORK_WORKFLOW.format(function_id=function_id),
            response=GetFunctionResponse,
            method="POST",
        )

    @staticmethod
    def _start_workflow_run_endpoint(function_id: str, run_id: str) -> NotteEndpoint[FunctionRunResponse]:
        return NotteEndpoint(
            path=AsyncWorkflowsClient.START_WORKFLOW_RUN.format(function_id=function_id, run_id=run_id),
            response=FunctionRunResponse,
            method="POST",
        )

    @staticmethod
    def _start_workflow_run_endpoint_without_run_id(function_id: str) -> NotteEndpoint[FunctionRunResponse]:
        return NotteEndpoint(
            path=AsyncWorkflowsClient.START_WORKFLOW_RUN_WITHOUT_RUN_ID.format(function_id=function_id),
            response=FunctionRunResponse,
            method="POST",
        )

    @staticmethod
    def _stop_workflow_run_endpoint(function_id: str, run_id: str) -> NotteEndpoint[UpdateFunctionRunResponse]:
        return NotteEndpoint(
            path=AsyncWorkflowsClient.STOP_WORKFLOW_RUN.format(function_id=function_id, run_id=run_id),
            response=UpdateFunctionRunResponse,
            method="DELETE",
        )

    @staticmethod
    def _get_workflow_run_endpoint(function_id: str, run_id: str) -> NotteEndpoint[GetFunctionRunResponse]:
        return NotteEndpoint(
            path=AsyncWorkflowsClient.GET_WORKFLOW_RUN.format(function_id=function_id, run_id=run_id),
            response=GetFunctionRunResponse,
            method="GET",
        )

    @staticmethod
    def _list_workflow_runs_endpoint(function_id: str) -> NotteEndpoint[ListFunctionRunsResponse]:
        return NotteEndpoint(
            path=AsyncWorkflowsClient.LIST_WORKFLOW_RUNS.format(function_id=function_id),
            response=ListFunctionRunsResponse,
            method="GET",
        )

    @staticmethod
    def _update_workflow_run_endpoint(function_id: str, run_id: str) -> NotteEndpoint[UpdateFunctionRunResponse]:
        return NotteEndpoint(
            path=AsyncWorkflowsClient.UPDATE_WORKFLOW_RUN.format(function_id=function_id, run_id=run_id),
            response=UpdateFunctionRunResponse,
            method="PATCH",
        )

    @staticmethod
    def _list_workflows_endpoint() -> NotteEndpoint[ListFunctionsResponse]:
        return NotteEndpoint(
            path=AsyncWorkflowsClient.LIST_WORKFLOWS,
            response=ListFunctionsResponse,
            method="GET",
        )

    @track_usage("cloud.workflow.create")
    async def create(self, **data: Unpack[CreateFunctionRequestDict]) -> GetFunctionResponse:
        """Create a new workflow."""
        request = CreateFunctionRequest.model_validate(data)
        endpoint = self._create_workflow_endpoint().with_file(request.path).with_request(request)
        return await self.request(endpoint)

    @track_usage("cloud.workflow.fork")
    async def fork(self, function_id: str) -> GetFunctionResponse:
        """Fork a workflow."""
        request = ForkFunctionRequest(function_id=function_id)
        endpoint = self._fork_workflow_endpoint(function_id).with_request(request)
        response = await self.request(endpoint)
        logger.info(f"[Function] {response.function_id} forked successfully from function_id={function_id}")
        return response

    @track_usage("cloud.workflow.update")
    async def update(
        self, function_id: str, restricted: bool = True, **data: Unpack[UpdateFunctionRequestDict]
    ) -> GetFunctionResponse:
        """Update an existing workflow."""
        request = UpdateFunctionRequest.model_validate(data)
        endpoint = self._update_workflow_endpoint(function_id, restricted=restricted).with_file(request.path)
        if request.version is not None:
            endpoint = endpoint.with_params(GetFunctionRequest(version=request.version))
        return await self.request(endpoint)

    @track_usage("cloud.workflow.get")
    async def get(self, function_id: str, **data: Unpack[GetFunctionRequestDict]) -> GetFunctionWithLinkResponse:
        """Get a workflow with download URL."""
        params = GetFunctionRequest.model_validate(data)
        return await self.request(self._get_workflow_endpoint(function_id).with_params(params))

    @track_usage("cloud.workflow.delete")
    async def delete(self, function_id: str) -> DeleteFunctionResponse:
        """Delete a workflow."""
        return await self.request(self._delete_workflow_endpoint(function_id))

    @track_usage("cloud.workflow.list")
    async def list(self, **data: Unpack[ListFunctionsRequestDict]) -> ListFunctionsResponse:
        """List all available workflows."""
        params = ListFunctionsRequest.model_validate(data)
        return await self.request(self._list_workflows_endpoint().with_params(params))

    async def create_run(self, function_id: str, local: bool = False) -> CreateFunctionRunResponse:
        """Create a new workflow run."""
        request = CreateFunctionRunRequest(local=local)
        return await self.request(self._create_workflow_run_endpoint(function_id).with_request(request))

    async def stop_run(self, function_id: str, run_id: str) -> UpdateFunctionRunResponse:
        """Stop a workflow run."""
        return await self.request(self._stop_workflow_run_endpoint(function_id, run_id))

    async def get_run(self, function_id: str, run_id: str) -> GetFunctionRunResponse:
        """Get a workflow run."""
        return await self.request(self._get_workflow_run_endpoint(function_id, run_id))

    async def update_run(
        self, function_id: str, run_id: str, **data: Unpack[FunctionRunUpdateRequestDict]
    ) -> UpdateFunctionRunResponse:
        """Update a workflow run."""
        request = FunctionRunUpdateRequest.model_validate(data)
        return await self.request(self._update_workflow_run_endpoint(function_id, run_id).with_request(request))

    async def list_runs(
        self, function_id: str, **data: Unpack[ListFunctionRunsRequestDict]
    ) -> ListFunctionRunsResponse:
        """List all workflow runs."""
        request = ListFunctionRunsRequest.model_validate(data)
        return await self.request(self._list_workflow_runs_endpoint(function_id).with_params(request))

    async def run(
        self, function_run_id: str, timeout: int | None = None, **data: Unpack[RunFunctionRequestDict]
    ) -> FunctionRunResponse:
        """Run a workflow."""
        _request = RunFunctionRequest.model_validate(data)
        request = StartFunctionRunRequest(
            function_id=_request.function_id,
            function_run_id=function_run_id,
            variables=_request.variables,
            stream=_request.stream,
        )
        endpoint = self._start_workflow_run_endpoint(
            function_id=request.function_id, run_id=function_run_id
        ).with_request(request)

        # For non-streaming, just make the request
        if not request.stream:
            return await self.request(endpoint, timeout=timeout or self.WORKFLOW_RUN_TIMEOUT)

        # For streaming, we need to handle the response differently
        # For now, return non-streaming result - streaming can be added later
        return await self.request(endpoint, timeout=timeout or self.WORKFLOW_RUN_TIMEOUT)

    def get_curl(self, function_id: str, **variables: Any) -> str:
        """Get curl command for running a workflow."""
        endpoint = self._start_workflow_run_endpoint_without_run_id(function_id=function_id)
        path = self.request_path(endpoint)
        variables_str = json.dumps(variables, indent=4)
        lines = variables_str.split("\n")
        indented_lines = [lines[0]] + ["    " + line for line in lines[1:]]
        indented_variables = "\n".join(indented_lines)
        return f"""curl --location '{path}' \\
--header 'x-notte-api-key: {self.token}' \\
--header 'Content-Type: application/json' \\
--header 'Authorization: Bearer {self.token}' \\
--data '{{
    "function_id": "{function_id}",
    "variables": {indented_variables}
}}'
"""


class AsyncRemoteWorkflow:
    """Async workflow that can be run on the cloud or locally.

    Workflows are saved in the notte console for easy access and versioning for users.
    """

    @deprecated("Workflow is deprecated, use Function instead")
    @overload
    def __init__(
        self, /, workflow_id: str, *, decryption_key: str | None = None, _client: "AsyncNotteClient | None" = None
    ) -> None: ...

    @deprecated("Workflow is deprecated, use Function instead")
    @overload
    def __init__(
        self,
        *,
        _client: "AsyncNotteClient | None" = None,
        workflow_path: str | None = None,
        **data: Unpack[CreateFunctionRequestDict],
    ) -> None: ...

    def __init__(  # pyright: ignore[reportInconsistentOverload]
        self,
        workflow_id: str | None = None,
        *,
        decryption_key: str | None = None,
        _client: "AsyncNotteClient | None" = None,
        workflow_path: str | None = None,
        **data: Unpack[CreateFunctionRequestDict],
    ) -> None:
        if _client is None:
            raise ValueError("AsyncNotteClient is required")
        self.client: AsyncWorkflowsClient = _client.workflows
        self.root_client: "AsyncNotteClient" = _client
        self._response: GetFunctionResponse | GetFunctionWithLinkResponse | None = None
        self._function_id: str | None = workflow_id
        self._session_id: str | None = None
        self._function_run_id: str | None = None
        self.decryption_key: str | None = decryption_key
        self._needs_create: bool = workflow_id is None
        self._workflow_path: str | None = workflow_path
        self._create_data: CreateFunctionRequestDict = data

    async def _ensure_created(self) -> None:
        """Ensure the workflow is created if needed."""
        if self._needs_create and self._response is None:
            path = self._get_final_path(self._create_data.get("path"), self._workflow_path)
            self._create_data["path"] = path
            self._response = await self.client.create(**self._create_data)
            self._function_id = self._response.function_id
            logger.info(f"[Function] {self._function_id} created successfully.")
            self._needs_create = False

    def _get_final_path(self, path: str | None, workflow_path: str | None) -> str:
        if path is not None and workflow_path is not None and path != workflow_path:
            raise ValueError("Cannot specify both 'path' and 'workflow_path' with different values")
        final_path = workflow_path or path
        if final_path is None:
            raise ValueError("Either 'workflow_path' or 'path' must be provided")
        if not final_path.endswith(".py"):
            raise ValueError(f"Code file path must end with .py, got '{final_path}'")
        return final_path

    @property
    async def response(self) -> GetFunctionResponse | GetFunctionWithLinkResponse:
        """Get the workflow response, fetching if needed."""
        await self._ensure_created()
        if self._response is not None:
            return self._response
        if self._function_id is None:
            raise ValueError("No function_id available")
        self._response = await self.client.get(function_id=self._function_id)
        logger.info(f"[Function] {self._response.function_id} metadata retrieved successfully.")
        return self._response

    @property
    def function_id(self) -> str:
        """Get the function ID."""
        if self._function_id is None:
            raise ValueError("Function not yet created. Call an async method first.")
        return self._function_id

    @property
    def workflow_id(self) -> str:
        """Get the workflow ID (alias for function_id)."""
        return self.function_id

    async def fork(self) -> "AsyncRemoteWorkflow":
        """Fork a shared workflow into your own private workflow."""
        await self._ensure_created()
        fork_response = await self.client.fork(function_id=self.function_id)
        return AsyncRemoteWorkflow(workflow_id=fork_response.function_id, _client=self.root_client)  # pyright: ignore[reportDeprecated]

    async def replay(self) -> MP4Replay:
        """Replay the workflow run."""
        if self._function_run_id is None:
            raise ValueError(
                "You should call `run` before calling `replay` (only available for remote workflow executions)"
            )
        if self._session_id is None:
            raise ValueError(
                f"Session ID not found in your function run {self._function_run_id}. Please check that your workflow is creating at least one `client.Session` in the `run` function."
            )
        return await self.root_client.sessions.replay(session_id=self._session_id)

    async def update(
        self,
        path: str | None = None,
        version: str | None = None,
        workflow_path: str | None = None,
        restricted: bool = True,
    ) -> None:
        """Update the workflow with a new code version."""
        await self._ensure_created()
        path = self._get_final_path(path, workflow_path)
        resp = await self.response
        self._response = await self.client.update(
            function_id=resp.function_id, path=path, version=version, restricted=restricted
        )
        logger.info(
            f"[Function] {self._response.function_id} updated successfully to version {self._response.latest_version}."
        )

    async def delete(self) -> None:
        """Delete the workflow from the notte console."""
        await self._ensure_created()
        resp = await self.response
        _ = await self.client.delete(function_id=resp.function_id)
        logger.info(f"[Function] {resp.function_id} deleted successfully.")

    async def get_url(self, version: str | None = None, decryption_key: str | None = None) -> str:
        """Get the download URL for the workflow code."""
        await self._ensure_created()
        resp = await self.response
        if not isinstance(resp, GetFunctionWithLinkResponse) or version != resp.latest_version:
            self._response = await self.client.get(function_id=resp.function_id, version=version)
            url = self._response.url
        else:
            url = resp.url

        decryption_key = decryption_key or self.decryption_key
        decrypted: bool = url.startswith("https://") or url.startswith("http://")
        if not decrypted:
            if decryption_key is None:
                raise ValueError(
                    "Decryption key is required to decrypt the function download url. Set the `AsyncNotteFunction(function_id='<your-function-id>', decryption_key='<your-key>')` when creating the function."
                )
            encryption = Encryption(root_key=decryption_key)
            url = encryption.decrypt(url)
            decrypted = url.startswith("https://") or url.startswith("http://")
            if not decrypted:
                raise ValueError(
                    f"Failed to decrypt function download url: {url}. Call support@notte.cc if you need help."
                )
            logger.info("🔐 Successfully decrypted function download url")
        return url

    async def download(
        self,
        workflow_path: str | None = None,
        version: str | None = None,
        decryption_key: str | None = None,
        path: str | None = None,
    ) -> str:
        """Download the function code from the notte console as a python file."""
        await self._ensure_created()
        final_path = None
        if path is not None or workflow_path is not None:
            final_path = self._get_final_path(path, workflow_path)

        file_url = await self.get_url(version=version, decryption_key=decryption_key)
        async with httpx.AsyncClient() as http_client:
            try:
                response = await http_client.get(file_url, timeout=30)
                _ = response.raise_for_status()
            except httpx.RequestError as e:
                raise ValueError(f"Failed to download function code from {file_url} in 30 seconds: {e}")

        code_content = response.text
        if final_path is None:
            return code_content
        with open(final_path, "w") as f:
            _ = f.write(code_content)
        resp = await self.response
        logger.info(f"[Function] {resp.function_id} downloaded successfully to {final_path}.")
        return code_content

    async def run(
        self,
        version: str | None = None,
        local: bool = False,
        restricted: bool = True,
        timeout: int | None = None,
        stream: bool = True,
        raise_on_failure: bool = True,
        function_run_id: str | None = None,
        workflow_run_id: str | None = None,
        log_callback: Callable[[str], None] | None = None,
        **variables: Any,
    ) -> FunctionRunResponse:
        """Run the function code using the specified version and variables."""
        await self._ensure_created()
        if workflow_run_id is not None:
            warnings.warn(
                "'workflow_run_id' is deprecated, use 'function_run_id' instead",
                DeprecationWarning,
                stacklevel=2,
            )
        if function_run_id is not None and workflow_run_id is not None and function_run_id != workflow_run_id:
            raise ValueError("Cannot specify both 'function_run_id' and 'workflow_run_id' with different values")
        function_run_id = function_run_id or workflow_run_id

        if function_run_id is None:
            create_run_response = await self.client.create_run(self.function_id, local=local)
            function_run_id = create_run_response.function_run_id

        if log_callback is not None and not local:
            raise ValueError("Log callback can only be set when running function code locally")

        self._function_run_id = function_run_id
        logger.info(
            f"[Function Run] {function_run_id} created and scheduled for {'local' if local else 'cloud'} execution with raise_on_failure={raise_on_failure}."
        )

        if local:
            code = await self.download(workflow_path=None, version=version)
            exception: Exception | None = None
            log_capture = LogCapture(write_callback=log_callback)
            try:
                with log_capture:
                    result = SecureScriptRunner(notte_module=self.root_client).run_script(  # pyright: ignore [reportArgumentType]
                        code, variables=variables, restricted=restricted
                    )
                    status = "closed"
            except Exception as e:
                import traceback

                logger.error(f"[Function] {self.function_id} run failed with error: {traceback.format_exc()}")
                result = str(e)
                status = "failed"
                exception = e

            self._session_id = log_capture.session_id
            _ = await self.client.update_run(
                function_id=self.function_id,
                run_id=function_run_id,
                result=str(result),
                variables=variables,
                status=status,
                session_id=log_capture.session_id,
                logs=log_capture.get_logs(),
            )
            if raise_on_failure and exception is not None:
                raise exception
            return FunctionRunResponse(
                function_id=self.function_id,
                function_run_id=function_run_id,
                session_id=log_capture.session_id,
                result=result,
                status=status,
            )

        resp = await self.response
        res = await self.client.run(
            function_id=resp.function_id,
            function_run_id=function_run_id,
            stream=stream,
            timeout=timeout,
            variables=variables,
        )
        if raise_on_failure and res.status == "failed":
            from notte_sdk.endpoints.workflows import FailedToRunCloudFunctionError

            raise FailedToRunCloudFunctionError(self.function_id, function_run_id, res)
        self._session_id = res.session_id
        return res

    async def stop_run(self, run_id: str) -> UpdateFunctionRunResponse:
        """Manually stop a function run by its ID."""
        await self._ensure_created()
        return await self.client.stop_run(function_id=self.function_id, run_id=run_id)

    async def get_run(self, run_id: str) -> GetFunctionRunResponse:
        """Get a function run by its ID."""
        await self._ensure_created()
        return await self.client.get_run(function_id=self.function_id, run_id=run_id)

    def get_curl(self, **variables: Any) -> str:
        """Convert the workflow/run to a curl request."""
        if self._function_id is None:
            raise ValueError("Function not yet created. Call an async method first.")
        return self.client.get_curl(function_id=self.function_id, **variables)


class AsyncNotteFunction(AsyncRemoteWorkflow):
    """Async function wrapper (preferred over AsyncRemoteWorkflow).

    Functions are saved in the notte console for easy access and versioning for users.
    This is a wrapper around AsyncRemoteWorkflow that uses function_id terminology.
    """

    @overload
    def __init__(
        self, /, function_id: str, *, decryption_key: str | None = None, _client: "AsyncNotteClient | None" = None
    ) -> None: ...

    @overload
    def __init__(
        self, *, _client: "AsyncNotteClient | None" = None, **data: Unpack[CreateFunctionRequestDict]
    ) -> None: ...

    def __init__(  # pyright: ignore[reportInconsistentOverload]
        self,
        function_id: str | None = None,
        *,
        decryption_key: str | None = None,
        _client: "AsyncNotteClient | None" = None,
        **data: Unpack[CreateFunctionRequestDict],
    ) -> None:
        if function_id is not None:
            super().__init__(function_id, decryption_key=decryption_key, _client=_client)  # pyright: ignore[reportDeprecated]
        else:
            super().__init__(_client=_client, **data)  # pyright: ignore[reportDeprecated]

    @override
    async def fork(self) -> "AsyncNotteFunction":
        """Fork a shared function into your own private function."""
        await self._ensure_created()
        fork_response = await self.client.fork(function_id=self.function_id)
        return AsyncNotteFunction(function_id=fork_response.function_id, _client=self.root_client)
