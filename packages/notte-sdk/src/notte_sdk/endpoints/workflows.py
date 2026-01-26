from __future__ import annotations

import json
import re
import traceback
import warnings
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar, Unpack, final, overload

import requests
from notte_core.ast import SecureScriptRunner
from notte_core.common.logging import logger
from notte_core.common.telemetry import track_usage
from notte_core.errors.base import NotteBaseError
from notte_core.utils.encryption import Encryption
from notte_core.utils.webp_replay import MP4Replay
from typing_extensions import deprecated

from notte_sdk.endpoints.base import BaseClient, NotteEndpoint
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
    from notte_sdk.client import NotteClient


@final
class FailedToRunCloudFunctionError(NotteBaseError):
    """
    Exception raised when a function run fails to run on the cloud.
    """

    def __init__(self, function_id: str, function_run_id: str, response: FunctionRunResponse):
        self.message = f"Function {function_id} with run_id={function_run_id} failed with result '{response.result}'"
        self.function_id = function_id
        self.function_run_id = function_run_id
        self.response = response
        super().__init__(
            user_message=self.message,
            agent_message=self.message,
            dev_message=self.message,
        )


@final
class WorkflowsClient(BaseClient):
    """
    Client for the Notte Workflows API.

    Note: this client is only able to handle one session at a time.
    If you need to handle multiple sessions, you need to create a new client for each session.
    """

    # Workflow endpoints
    CREATE_WORKFLOW = ""
    FORK_WORKFLOW = "{function_id}/fork"
    UPDATE_WORKFLOW = "{function_id}?restricted={restricted}"
    GET_WORKFLOW = "{function_id}"
    DELETE_WORKFLOW = "{function_id}"
    LIST_WORKFLOWS = ""

    # RUN endpoints ...
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
        root_client: "NotteClient",
        api_key: str | None = None,
        server_url: str | None = None,
        verbose: bool = False,
    ):
        """
        Initialize a WorkflowsClient instance.

        Initializes the client with an optional API key for workflow management.
        """
        super().__init__(
            root_client=root_client,
            base_endpoint_path="workflows",
            server_url=server_url,
            api_key=api_key,
            verbose=verbose,
        )

    @staticmethod
    def _create_workflow_endpoint() -> NotteEndpoint[GetFunctionResponse]:
        """
        Returns a NotteEndpoint configured for creating a new workflow.

        Returns:
            A NotteEndpoint with the POST method that expects a GetFunctionResponse.
        """
        return NotteEndpoint(
            path=WorkflowsClient.CREATE_WORKFLOW,
            response=GetFunctionResponse,
            method="POST",
        )

    @staticmethod
    def _update_workflow_endpoint(function_id: str, restricted: bool = True) -> NotteEndpoint[GetFunctionResponse]:
        """
        Returns a NotteEndpoint configured for updating a workflow.

        Args:
            function_id: The ID of the workflow to update.

        Returns:
            A NotteEndpoint with the POST method that expects a GetFunctionResponse.
        """
        return NotteEndpoint(
            path=WorkflowsClient.UPDATE_WORKFLOW.format(function_id=function_id, restricted=restricted),
            response=GetFunctionResponse,
            method="POST",
        )

    @staticmethod
    def _get_workflow_endpoint(function_id: str) -> NotteEndpoint[GetFunctionWithLinkResponse]:
        """
        Returns a NotteEndpoint configured for getting a workflow with download URL.

        Args:
            function_id: The ID of the workflow to get.

        Returns:
            A NotteEndpoint with the GET method that expects a GetFunctionWithLinkResponse.
        """
        return NotteEndpoint(
            path=WorkflowsClient.GET_WORKFLOW.format(function_id=function_id),
            response=GetFunctionWithLinkResponse,
            method="GET",
        )

    @staticmethod
    def _delete_workflow_endpoint(function_id: str) -> NotteEndpoint[DeleteFunctionResponse]:
        """
        Returns a NotteEndpoint configured for deleting a workflow.

        Args:
            function_id: The ID of the workflow to delete.

        Returns:
            A NotteEndpoint with the DELETE method.
        """
        return NotteEndpoint(
            path=WorkflowsClient.DELETE_WORKFLOW.format(function_id=function_id),
            response=DeleteFunctionResponse,
            method="DELETE",
        )

    @staticmethod
    def _create_workflow_run_endpoint(function_id: str) -> NotteEndpoint[CreateFunctionRunResponse]:
        """
        Returns a NotteEndpoint configured for creating a new workflow run.
        """
        return NotteEndpoint(
            path=WorkflowsClient.CREATE_WORKFLOW_RUN.format(function_id=function_id),
            response=CreateFunctionRunResponse,
            method="POST",
        )

    @staticmethod
    def _fork_workflow_endpoint(function_id: str) -> NotteEndpoint[GetFunctionResponse]:
        """
        Returns a NotteEndpoint configured for forking a workflow.
        """
        return NotteEndpoint(
            path=WorkflowsClient.FORK_WORKFLOW.format(function_id=function_id),
            response=GetFunctionResponse,
            method="POST",
        )

    @staticmethod
    def _start_workflow_run_endpoint(function_id: str, run_id: str) -> NotteEndpoint[FunctionRunResponse]:
        """
        Returns a NotteEndpoint configured for starting a new workflow run.
        """
        return NotteEndpoint(
            path=WorkflowsClient.START_WORKFLOW_RUN.format(function_id=function_id, run_id=run_id),
            response=FunctionRunResponse,
            method="POST",
        )

    @staticmethod
    def _start_workflow_run_endpoint_without_run_id(function_id: str) -> NotteEndpoint[FunctionRunResponse]:
        """
        Returns a NotteEndpoint configured for starting a new workflow run.
        """
        return NotteEndpoint(
            path=WorkflowsClient.START_WORKFLOW_RUN_WITHOUT_RUN_ID.format(function_id=function_id),
            response=FunctionRunResponse,
            method="POST",
        )

    @staticmethod
    def _stop_workflow_run_endpoint(function_id: str, run_id: str) -> NotteEndpoint[UpdateFunctionRunResponse]:
        """
        Returns a NotteEndpoint configured for stopping a workflow run.
        """
        return NotteEndpoint(
            path=WorkflowsClient.STOP_WORKFLOW_RUN.format(function_id=function_id, run_id=run_id),
            response=UpdateFunctionRunResponse,
            method="DELETE",
        )

    @staticmethod
    def _get_workflow_run_endpoint(function_id: str, run_id: str) -> NotteEndpoint[GetFunctionRunResponse]:
        """
        Returns a NotteEndpoint configured for getting a workflow run.
        """
        return NotteEndpoint(
            path=WorkflowsClient.GET_WORKFLOW_RUN.format(function_id=function_id, run_id=run_id),
            response=GetFunctionRunResponse,
            method="GET",
        )

    @staticmethod
    def _list_workflow_runs_endpoint(function_id: str) -> NotteEndpoint[ListFunctionRunsResponse]:
        """
        Returns a NotteEndpoint configured for listing all workflow runs.
        """
        return NotteEndpoint(
            path=WorkflowsClient.LIST_WORKFLOW_RUNS.format(function_id=function_id),
            response=ListFunctionRunsResponse,
            method="GET",
        )

    @staticmethod
    def _update_workflow_run_endpoint(function_id: str, run_id: str) -> NotteEndpoint[UpdateFunctionRunResponse]:
        """
        Returns a NotteEndpoint configured for updating a workflow run.
        """
        return NotteEndpoint(
            path=WorkflowsClient.UPDATE_WORKFLOW_RUN.format(function_id=function_id, run_id=run_id),
            response=UpdateFunctionRunResponse,
            method="PATCH",
        )

    @staticmethod
    def _list_workflows_endpoint() -> NotteEndpoint[ListFunctionsResponse]:
        """
        Returns a NotteEndpoint configured for listing all workflows.

        Returns:
            A NotteEndpoint with the GET method that expects a ListFunctionsResponse.
        """
        return NotteEndpoint(
            path=WorkflowsClient.LIST_WORKFLOWS,
            response=ListFunctionsResponse,
            method="GET",
        )

    @track_usage("cloud.workflow.create")
    def create(self, **data: Unpack[CreateFunctionRequestDict]) -> GetFunctionResponse:
        """
        Create a new workflow.

        Args:
            **data: Unpacked dictionary containing the workflow creation parameters.

        Returns:
            GetFunctionResponse: The created workflow information.
        """
        request = CreateFunctionRequest.model_validate(data)
        endpoint = self._create_workflow_endpoint().with_file(request.path).with_request(request)
        response = self.request(endpoint)
        return response

    @track_usage("cloud.workflow.fork")
    def fork(self, function_id: str) -> GetFunctionResponse:
        """
        Fork a workflow.
        """
        request = ForkFunctionRequest(function_id=function_id)
        endpoint = self._fork_workflow_endpoint(function_id).with_request(request)
        response = self.request(endpoint)
        logger.info(f"[Function] {response.function_id} forked successfully from function_id={function_id}")
        return response

    @track_usage("cloud.workflow.update")
    def update(
        self, function_id: str, restricted: bool = True, **data: Unpack[UpdateFunctionRequestDict]
    ) -> GetFunctionResponse:
        """
        Update an existing workflow.

        Args:
            function_id: The ID of the workflow to update.
            **data: Unpacked dictionary containing the workflow update parameters.

        Returns:
            GetFunctionResponse: The updated workflow information.
        """
        request = UpdateFunctionRequest.model_validate(data)
        endpoint = self._update_workflow_endpoint(function_id, restricted=restricted).with_file(request.path)
        if request.version is not None:
            endpoint = endpoint.with_params(GetFunctionRequest(version=request.version))
        response = self.request(endpoint)
        return response

    @track_usage("cloud.workflow.get")
    def get(self, function_id: str, **data: Unpack[GetFunctionRequestDict]) -> GetFunctionWithLinkResponse:
        """
        Get a workflow with download URL.

        Args:
            function_id: The ID of the workflow to get.
            **data: Unpacked dictionary containing parameters for the request.

        Returns:
            GetFunctionWithLinkResponse: Response containing the workflow information and download URL.
        """
        params = GetFunctionRequest.model_validate(data)
        response = self.request(self._get_workflow_endpoint(function_id).with_params(params))
        return response

    @track_usage("cloud.workflow.delete")
    def delete(self, function_id: str) -> DeleteFunctionResponse:
        """
        Delete a workflow.

        Args:
            function_id: The ID of the workflow to delete.
        """
        return self.request(self._delete_workflow_endpoint(function_id))

    @track_usage("cloud.workflow.list")
    def list(self, **data: Unpack[ListFunctionsRequestDict]) -> ListFunctionsResponse:
        """
        List all available workflows.

        Args:
            **data: Unpacked dictionary containing parameters for the request.

        Returns:
            ListFunctionsResponse: Response containing the list of workflows.
        """
        params = ListFunctionsRequest.model_validate(data)
        return self.request(self._list_workflows_endpoint().with_params(params))

    def create_run(self, function_id: str, local: bool = False) -> CreateFunctionRunResponse:
        request = CreateFunctionRunRequest(local=local)
        return self.request(self._create_workflow_run_endpoint(function_id).with_request(request))

    def stop_run(self, function_id: str, run_id: str) -> UpdateFunctionRunResponse:
        return self.request(self._stop_workflow_run_endpoint(function_id, run_id))

    def get_run(self, function_id: str, run_id: str) -> GetFunctionRunResponse:
        return self.request(self._get_workflow_run_endpoint(function_id, run_id))

    def update_run(
        self, function_id: str, run_id: str, **data: Unpack[FunctionRunUpdateRequestDict]
    ) -> UpdateFunctionRunResponse:
        request = FunctionRunUpdateRequest.model_validate(data)
        return self.request(self._update_workflow_run_endpoint(function_id, run_id).with_request(request))

    def list_runs(self, function_id: str, **data: Unpack[ListFunctionRunsRequestDict]) -> ListFunctionRunsResponse:
        """
        List all workflow runs.

        Use `list_runs(only_active=False)` to retrieve all runs, including completed ones.
        """
        request = ListFunctionRunsRequest.model_validate(data)
        return self.request(self._list_workflow_runs_endpoint(function_id).with_params(request))

    @staticmethod
    def decode_message(text: str):
        # Convert ANSI color codes to loguru color tags
        colored_text = WorkflowsClient._ansi_to_loguru_colors(text)

        split = colored_text.split("|", 3)

        return split[-1].strip()

    @staticmethod
    def _ansi_to_loguru_colors(text: str) -> str:
        """
        Convert ANSI color codes to loguru color tags.
        Properly handles multiple colors and styles within a single line.
        """
        # ANSI color code to loguru tag mapping
        color_codes = {
            "30": "<k>",  # Black
            "31": "<r>",  # Red
            "32": "<g>",  # Green
            "33": "<y>",  # Yellow
            "34": "<e>",  # Blue
            "35": "<m>",  # Magenta
            "36": "<c>",  # Cyan
            "37": "<w>",  # White
        }

        # Track currently open tags
        open_tags: list[str] = []
        result_parts: list[str] = []

        # Pattern to match ANSI escape sequences
        ansi_pattern = r"\x1b\[([0-9;]*)m"

        # Split text by ANSI sequences while keeping the sequences
        parts = re.split(ansi_pattern, text)

        i = 0
        while i < len(parts):
            if i % 2 == 0:
                # This is text content
                if parts[i]:
                    result_parts.append(parts[i])
            else:
                # This is an ANSI code
                codes = parts[i].split(";") if parts[i] else ["0"]

                for code in codes:
                    code = code.strip()

                    if code == "0":
                        # Reset all - close all open tags
                        if open_tags:
                            result_parts.append("</>")
                            open_tags.clear()
                    elif code in color_codes:
                        # Color code - open tag if not already open
                        tag = color_codes[code]
                        if tag not in open_tags:
                            result_parts.append(tag)
                            open_tags.append(tag)
                    # Ignore other codes (like '1' for bold)

            i += 1

        # Close any remaining open tags at the end
        if open_tags:
            result_parts.append("</>")

        return "".join(result_parts)

    def run(
        self, function_run_id: str, timeout: int | None = None, **data: Unpack[RunFunctionRequestDict]
    ) -> FunctionRunResponse:
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

        headers = {"x-notte-api-key": self.token}
        headers["Content-Type"] = "application/json"
        headers = self.headers(headers=headers)
        url = self.request_path(endpoint)
        req_data = request.model_dump_json(exclude_none=True)
        timeout = timeout or self.WORKFLOW_RUN_TIMEOUT

        if not request.stream:
            res = requests.post(url=url, headers=headers, data=req_data, timeout=timeout, stream=True)
            return FunctionRunResponse.model_validate(res.json())

        INITIAL = object()
        result: Any = INITIAL

        session_id = None
        with requests.post(url=url, headers=headers, data=req_data, timeout=timeout, stream=True) as res:
            res.raise_for_status()
            for line in res.iter_lines():
                if not line:  # Skip empty lines
                    continue

                try:
                    # Lambda streaming often uses Server-Sent Events format
                    utf = line.decode("utf-8")
                    if utf.startswith("data: "):
                        message = json.loads(utf[6:])
                        log_msg = message.get("message", "")
                        decoded = WorkflowsClient.decode_message(log_msg)

                        if message["type"] == "log":
                            try:
                                logger.opt(colors=True).info(decoded)
                            except Exception:
                                logger.info(decoded)
                        elif message["type"] == "result":
                            result = log_msg
                        elif message["type"] == "session_start":
                            session_id = log_msg

                            logger.info(
                                f"Live viewer for session available at: https://api.notte.cc/sessions/viewer/index.html?ws=wss://api.notte.cc/sessions/{session_id}/debug/recording?token={self.token}"
                            )

                except json.JSONDecodeError:
                    continue

        if result is INITIAL:
            raise ValueError("Did not get any result from workflow")

        return FunctionRunResponse.model_validate_json(result)

    def get_curl(self, function_id: str, **variables: Any) -> str:
        endpoint = self._start_workflow_run_endpoint_without_run_id(function_id=function_id)
        path = self.request_path(endpoint)
        variables_str = json.dumps(variables, indent=4)
        # Indent the variables JSON to align with the surrounding structure (skip first line)
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


class RemoteWorkflow:
    """
    Notte workflow that can be run on the cloud or locally.

    Workflows are saved in the notte console for easy access and versioning for users.
    """

    @deprecated("Workflow is deprecated, use Function instead")
    @overload
    def __init__(
        self, /, workflow_id: str, *, decryption_key: str | None = None, _client: NotteClient | None = None
    ) -> None: ...

    @deprecated("Workflow is deprecated, use Function instead")
    @overload
    def __init__(
        self,
        *,
        _client: NotteClient | None = None,
        workflow_path: str | None = None,
        **data: Unpack[CreateFunctionRequestDict],
    ) -> None: ...

    def __init__(  # pyright: ignore[reportInconsistentOverload]
        self,
        workflow_id: str | None = None,
        *,
        decryption_key: str | None = None,
        _client: NotteClient | None = None,
        workflow_path: str | None = None,
        **data: Unpack[CreateFunctionRequestDict],
    ) -> None:
        if _client is None:
            raise ValueError("NotteClient is required")
        # init attributes
        self.client: WorkflowsClient = _client.workflows
        self.root_client: NotteClient = _client
        self._response: GetFunctionResponse | GetFunctionWithLinkResponse | None = None
        if workflow_id is None:
            data["path"] = self._get_final_path(data.get("path"), workflow_path)
            self._response = _client.workflows.create(**data)
            workflow_id = self._response.function_id
            logger.info(f"[Function] {workflow_id} created successfully.")
        self._function_id: str = workflow_id
        self._session_id: str | None = None
        self._function_run_id: str | None = None
        self.decryption_key: str | None = decryption_key

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
    def response(self) -> GetFunctionResponse | GetFunctionWithLinkResponse:
        if self._response is not None:
            return self._response
        self._response = self.client.get(function_id=self._function_id)
        logger.info(f"[Function] {self._response.function_id} metadata retrieved successfully.")
        return self._response

    def fork(self) -> "RemoteWorkflow":
        """
        Fork a shared workflow into your own private workflow.

        ```python
        function = notte.Function("<user-shared-workflow-id>")
        forked_function = function.fork()
        forked_function.run()
        ```

        The forked workflow is only accessible to you and you can update it as you want.
        """
        fork_response = self.client.fork(function_id=self._function_id)
        return RemoteWorkflow(workflow_id=fork_response.function_id, _client=self.root_client)  # pyright: ignore[reportDeprecated]

    @property
    def function_id(self) -> str:
        return self.response.function_id

    @property
    def workflow_id(self) -> str:
        return self.response.workflow_id

    def replay(self) -> MP4Replay:
        """
        Replay the workflow run.

        ```python
        function = notte.Function("<your-function-id>")
        function.run()
        replay = function.replay()
        replay.save("run_replay.webp")
        ```
        """
        if self._function_run_id is None:
            raise ValueError(
                "You should call `run` before calling `replay` (only available for remote workflow executions)"
            )
        if self._session_id is None:
            raise ValueError(
                f"Session ID not found in your function run {self._function_run_id}. Please check that your workflow is creating at least one `client.Session` in the `run` function."
            )
        return self.root_client.sessions.replay(session_id=self._session_id)

    def update(
        self,
        path: str | None = None,
        version: str | None = None,
        workflow_path: str | None = None,
        restricted: bool = True,
    ) -> None:
        """
        Update the workflow with a a new code version.

        ```python
        function = notte.Function("<your-function-id>")
        function.update(path="<path-to-your-function.py>")
        ```

        If you set a version, only that version will be updated.
        """
        path = self._get_final_path(path, workflow_path)
        self._response = self.client.update(
            function_id=self.response.function_id, path=path, version=version, restricted=restricted
        )
        logger.info(
            f"[Function] {self.response.function_id} updated successfully to version {self.response.latest_version}."
        )

    def delete(self) -> None:
        """
        Delete the workflow from the notte console.

        ```python
        function = notte.Function("<your-function-id>")
        function.delete()
        ```
        """
        _ = self.client.delete(function_id=self.response.function_id)
        logger.info(f"[Function] {self.response.function_id} deleted successfully.")

    def get_url(self, version: str | None = None, decryption_key: str | None = None) -> str:
        if not isinstance(self.response, GetFunctionWithLinkResponse) or version != self.response.latest_version:
            self._response = self.client.get(function_id=self.response.function_id, version=version)
            url = self._response.url
        else:
            url = self.response.url

        decryption_key = decryption_key or self.decryption_key
        decrypted: bool = url.startswith("https://") or url.startswith("http://")
        if not decrypted:
            if decryption_key is None:
                raise ValueError(
                    "Decryption key is required to decrypt the function download url. Set the `notte.Function(function_id='<your-function-id>', decryption_key='<your-key>')` when creating the function."
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

    def download(
        self,
        workflow_path: str | None = None,
        version: str | None = None,
        decryption_key: str | None = None,
        path: str | None = None,
    ) -> str:
        """
        Download the function code from the notte console as a python file.

        ```python
        function = notte.Function("<your-function-id>")
        function.download(path="<path-to-your-function.py>", decryption_key="<your-key>")
        ```

        """
        final_path = None
        if path is not None or workflow_path is not None:
            final_path = self._get_final_path(path, workflow_path)

        file_url = self.get_url(version=version, decryption_key=decryption_key)
        try:
            response = requests.get(file_url, timeout=self.client.DEFAULT_REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
        except requests.RequestException as e:
            raise ValueError(f"Failed to download function code from {file_url} in 30 seconds: {e}")

        code_content = response.text
        if final_path is None:
            return code_content
        with open(final_path, "w") as f:
            _ = f.write(code_content)
        logger.info(f"[Function] {self.response.function_id} downloaded successfully to {final_path}.")
        return code_content

    def run(
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
        """
        Run the function code using the specified version and variables.

        If no version is provided, the latest version is used.

        ```python
        function = notte.Function("<your-function-id>")
        function.run(variable1="value1", variable2="value2")
        ```

        > Make sure that the correct variables are provided based on the python file previously uploaded. Otherwise, the workflow will fail.
        """
        if workflow_run_id is not None:
            warnings.warn(
                "'workflow_run_id' is deprecated, use 'function_run_id' instead",
                DeprecationWarning,
                stacklevel=2,
            )
        if function_run_id is not None and workflow_run_id is not None and function_run_id != workflow_run_id:
            raise ValueError("Cannot specify both 'function_run_id' and 'workflow_run_id' with different values")
        function_run_id = function_run_id or workflow_run_id
        # first create the run on DB
        if function_run_id is None:
            create_run_response = self.client.create_run(self.function_id, local=local)
            function_run_id = create_run_response.function_run_id

        if log_callback is not None and not local:
            raise ValueError("Log callback can only set when running function code locally")

        self._function_run_id = function_run_id
        logger.info(
            f"[Function Run] {function_run_id} created and scheduled for {'local' if local else 'cloud'} execution with raise_on_failure={raise_on_failure}."
        )
        if local:
            code = self.download(workflow_path=None, version=version)
            exception: Exception | None = None
            log_capture = LogCapture(write_callback=log_callback)
            try:
                with log_capture:
                    result = SecureScriptRunner(notte_module=self.root_client).run_script(  # pyright: ignore [reportArgumentType]
                        code, variables=variables, restricted=restricted
                    )
                    status = "closed"
            except Exception as e:
                logger.error(f"[Function] {self.function_id} run failed with error: {traceback.format_exc()}")
                result = str(e)
                status = "failed"
                exception = e
            # update the run with the result
            self._session_id = log_capture.session_id
            _ = self.client.update_run(
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
        # run on cloud
        res = self.client.run(
            function_id=self.response.function_id,
            function_run_id=function_run_id,
            stream=stream,
            timeout=timeout,
            variables=variables,
        )
        if raise_on_failure and res.status == "failed":
            raise FailedToRunCloudFunctionError(self.function_id, function_run_id, res)
        self._session_id = res.session_id
        return res

    def stop_run(self, run_id: str) -> UpdateFunctionRunResponse:
        """
        Manually stop a function run by its ID.

        """
        return self.client.stop_run(function_id=self.function_id, run_id=run_id)

    def get_run(self, run_id: str) -> GetFunctionRunResponse:
        """
        Get a function run by its ID.

        """
        return self.client.get_run(function_id=self.function_id, run_id=run_id)

    def get_curl(self, **variables: Any) -> str:
        """
        Convert the workflow/run to a curl request.

        """
        return self.client.get_curl(function_id=self.function_id, **variables)
