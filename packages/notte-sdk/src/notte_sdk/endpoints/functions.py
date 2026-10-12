from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, ClassVar, Unpack, final, overload

import requests
from notte_core.common.logging import logger
from notte_core.common.telemetry import track_usage
from notte_core.errors.base import NotteBaseError
from pydantic import TypeAdapter

from notte_sdk.endpoints.base import BaseClient, NotteEndpoint
from notte_sdk.endpoints.run_payloads import PayloadMode, RunUpdateBody, offload_run_fields, resolve_run_fields
from notte_sdk.endpoints.sessions import SessionsClient
from notte_sdk.types import (
    CreateFunctionRequest,
    CreateFunctionRequestDict,
    CreateFunctionRunRequest,
    CreateFunctionRunResponse,
    DeleteFunctionResponse,
    ForkFunctionRequest,
    FunctionRunResponse,
    FunctionRuntime,
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
    ReplayResponse,
    RunFunctionRequest,
    RunFunctionRequestDict,
    StartFunctionRunRequest,
    UpdateFunctionRequest,
    UpdateFunctionRequestDict,
    UpdateFunctionRunResponse,
)

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
class FunctionsClient(BaseClient):
    """
    Client for the Notte Functions API.

    Note: this client is only able to handle one session at a time.
    If you need to handle multiple sessions, you need to create a new client for each session.
    """

    # Function endpoints
    CREATE_FUNCTION = ""
    FORK_FUNCTION = "{function_id}/fork"
    UPDATE_FUNCTION = "{function_id}?restricted={restricted}"
    GET_FUNCTION = "{function_id}"
    DELETE_FUNCTION = "{function_id}"
    LIST_FUNCTIONS = ""

    # RUN endpoints ...
    CREATE_FUNCTION_RUN = "{function_id}/runs/create"
    START_FUNCTION_RUN_WITHOUT_RUN_ID = "{function_id}/runs/start"
    STOP_FUNCTION_RUN = "{function_id}/runs/{run_id}"
    START_FUNCTION_RUN = "{function_id}/runs/{run_id}"
    GET_FUNCTION_RUN = "{function_id}/runs/{run_id}"
    LIST_FUNCTION_RUNS = "{function_id}/runs/"
    UPDATE_FUNCTION_RUN = "{function_id}/runs/{run_id}"
    RUN_FUNCTION_ENDPOINT = "{function_id}/runs/{run_id}"

    FUNCTION_RUN_TIMEOUT: ClassVar[int] = 60 * 5  # 5 minutes

    def __init__(
        self,
        root_client: "NotteClient",
        api_key: str | None = None,
        server_url: str | None = None,
        verbose: bool = False,
    ):
        """
        Initialize a FunctionsClient instance.

        Initializes the client with an optional API key for function management.
        """
        super().__init__(
            root_client=root_client,
            base_endpoint_path="functions",
            server_url=server_url,
            api_key=api_key,
            verbose=verbose,
        )

    @staticmethod
    def _create_function_endpoint() -> NotteEndpoint[GetFunctionResponse]:
        """
        Returns a NotteEndpoint configured for creating a new function.

        Returns:
            A NotteEndpoint with the POST method that expects a GetFunctionResponse.
        """
        return NotteEndpoint(
            path=FunctionsClient.CREATE_FUNCTION,
            response=GetFunctionResponse,
            method="POST",
        )

    @staticmethod
    def _update_function_endpoint(function_id: str, restricted: bool = True) -> NotteEndpoint[GetFunctionResponse]:
        """
        Returns a NotteEndpoint configured for updating a function.

        Args:
            function_id: The ID of the function to update.

        Returns:
            A NotteEndpoint with the POST method that expects a GetFunctionResponse.
        """
        return NotteEndpoint(
            path=FunctionsClient.UPDATE_FUNCTION.format(function_id=function_id, restricted=restricted),
            response=GetFunctionResponse,
            method="POST",
        )

    @staticmethod
    def _get_function_endpoint(function_id: str) -> NotteEndpoint[GetFunctionWithLinkResponse]:
        """
        Returns a NotteEndpoint configured for getting a function with download URL.

        Args:
            function_id: The ID of the function to get.

        Returns:
            A NotteEndpoint with the GET method that expects a GetFunctionWithLinkResponse.
        """
        return NotteEndpoint(
            path=FunctionsClient.GET_FUNCTION.format(function_id=function_id),
            response=GetFunctionWithLinkResponse,
            method="GET",
        )

    @staticmethod
    def _delete_function_endpoint(function_id: str) -> NotteEndpoint[DeleteFunctionResponse]:
        """
        Returns a NotteEndpoint configured for deleting a function.

        Args:
            function_id: The ID of the function to delete.

        Returns:
            A NotteEndpoint with the DELETE method.
        """
        return NotteEndpoint(
            path=FunctionsClient.DELETE_FUNCTION.format(function_id=function_id),
            response=DeleteFunctionResponse,
            method="DELETE",
        )

    @staticmethod
    def _create_function_run_endpoint(function_id: str) -> NotteEndpoint[CreateFunctionRunResponse]:
        """
        Returns a NotteEndpoint configured for creating a new function run.
        """
        return NotteEndpoint(
            path=FunctionsClient.CREATE_FUNCTION_RUN.format(function_id=function_id),
            response=CreateFunctionRunResponse,
            method="POST",
        )

    @staticmethod
    def _fork_function_endpoint(function_id: str) -> NotteEndpoint[GetFunctionResponse]:
        """
        Returns a NotteEndpoint configured for forking a function.
        """
        return NotteEndpoint(
            path=FunctionsClient.FORK_FUNCTION.format(function_id=function_id),
            response=GetFunctionResponse,
            method="POST",
        )

    @staticmethod
    def _start_function_run_endpoint(function_id: str, run_id: str) -> NotteEndpoint[FunctionRunResponse]:
        """
        Returns a NotteEndpoint configured for starting a new function run.
        """
        return NotteEndpoint(
            path=FunctionsClient.START_FUNCTION_RUN.format(function_id=function_id, run_id=run_id),
            response=FunctionRunResponse,
            method="POST",
        )

    @staticmethod
    def _start_function_run_endpoint_without_run_id(function_id: str) -> NotteEndpoint[FunctionRunResponse]:
        """
        Returns a NotteEndpoint configured for starting a new function run.
        """
        return NotteEndpoint(
            path=FunctionsClient.START_FUNCTION_RUN_WITHOUT_RUN_ID.format(function_id=function_id),
            response=FunctionRunResponse,
            method="POST",
        )

    @staticmethod
    def _stop_function_run_endpoint(function_id: str, run_id: str) -> NotteEndpoint[UpdateFunctionRunResponse]:
        """
        Returns a NotteEndpoint configured for stopping a function run.
        """
        return NotteEndpoint(
            path=FunctionsClient.STOP_FUNCTION_RUN.format(function_id=function_id, run_id=run_id),
            response=UpdateFunctionRunResponse,
            method="DELETE",
        )

    @staticmethod
    def _get_function_run_endpoint(function_id: str, run_id: str) -> NotteEndpoint[GetFunctionRunResponse]:
        """
        Returns a NotteEndpoint configured for getting a function run.
        """
        return NotteEndpoint(
            path=FunctionsClient.GET_FUNCTION_RUN.format(function_id=function_id, run_id=run_id),
            response=GetFunctionRunResponse,
            method="GET",
        )

    @staticmethod
    def _list_function_runs_endpoint(function_id: str) -> NotteEndpoint[ListFunctionRunsResponse]:
        """
        Returns a NotteEndpoint configured for listing all function runs.
        """
        return NotteEndpoint(
            path=FunctionsClient.LIST_FUNCTION_RUNS.format(function_id=function_id),
            response=ListFunctionRunsResponse,
            method="GET",
        )

    @staticmethod
    def _update_function_run_endpoint(function_id: str, run_id: str) -> NotteEndpoint[UpdateFunctionRunResponse]:
        """
        Returns a NotteEndpoint configured for updating a function run.
        """
        return NotteEndpoint(
            path=FunctionsClient.UPDATE_FUNCTION_RUN.format(function_id=function_id, run_id=run_id),
            response=UpdateFunctionRunResponse,
            method="PATCH",
        )

    @staticmethod
    def _list_functions_endpoint() -> NotteEndpoint[ListFunctionsResponse]:
        """
        Returns a NotteEndpoint configured for listing all functions.

        Returns:
            A NotteEndpoint with the GET method that expects a ListFunctionsResponse.
        """
        return NotteEndpoint(
            path=FunctionsClient.LIST_FUNCTIONS,
            response=ListFunctionsResponse,
            method="GET",
        )

    @track_usage("cloud.function.create")
    def create(self, **data: Unpack[CreateFunctionRequestDict]) -> GetFunctionResponse:
        """
        Create a new function.

        Args:
            **data: Unpacked dictionary containing the function creation parameters.

        Returns:
            GetFunctionResponse: The created function information.
        """
        request = CreateFunctionRequest.model_validate(data)
        endpoint = self._create_function_endpoint().with_file(request.path).with_request(request)
        response = self.request(endpoint)
        return response

    @track_usage("cloud.function.fork")
    def fork(self, function_id: str) -> GetFunctionResponse:
        """
        Fork a function.
        """
        request = ForkFunctionRequest(function_id=function_id)
        endpoint = self._fork_function_endpoint(function_id).with_request(request)
        response = self.request(endpoint)
        logger.info(f"[Function] {response.function_id} forked successfully from function_id={function_id}")
        return response

    @track_usage("cloud.function.update")
    def update(
        self, function_id: str, restricted: bool = True, **data: Unpack[UpdateFunctionRequestDict]
    ) -> GetFunctionResponse:
        """
        Update an existing function.

        Args:
            function_id: The ID of the function to update.
            **data: Unpacked dictionary containing the function update parameters.

        Returns:
            GetFunctionResponse: The updated function information.
        """
        request = UpdateFunctionRequest.model_validate(data)
        endpoint = self._update_function_endpoint(function_id, restricted=restricted).with_file(request.path)
        if request.version is not None:
            endpoint = endpoint.with_params(GetFunctionRequest(version=request.version))
        response = self.request(endpoint)
        return response

    @track_usage("cloud.function.get")
    def get(self, function_id: str, **data: Unpack[GetFunctionRequestDict]) -> GetFunctionWithLinkResponse:
        """
        Get a function with download URL.

        Args:
            function_id: The ID of the function to get.
            **data: Unpacked dictionary containing parameters for the request.

        Returns:
            GetFunctionWithLinkResponse: Response containing the function information and download URL.
        """
        params = GetFunctionRequest.model_validate(data)
        response = self.request(self._get_function_endpoint(function_id).with_params(params))
        return response

    @track_usage("cloud.function.delete")
    def delete(self, function_id: str) -> DeleteFunctionResponse:
        """
        Delete a function.

        Args:
            function_id: The ID of the function to delete.
        """
        return self.request(self._delete_function_endpoint(function_id))

    @track_usage("cloud.function.list")
    def list(self, **data: Unpack[ListFunctionsRequestDict]) -> ListFunctionsResponse:
        """
        List all available functions.

        Args:
            **data: Unpacked dictionary containing parameters for the request.

        Returns:
            ListFunctionsResponse: Response containing the list of functions.
        """
        params = ListFunctionsRequest.model_validate(data)
        return self.request(self._list_functions_endpoint().with_params(params))

    def create_run(self, function_id: str) -> CreateFunctionRunResponse:
        request = CreateFunctionRunRequest()
        return self.request(self._create_function_run_endpoint(function_id).with_request(request))

    def stop_run(self, function_id: str, run_id: str) -> UpdateFunctionRunResponse:
        return self.request(self._stop_function_run_endpoint(function_id, run_id))

    def get_run(self, function_id: str, run_id: str) -> GetFunctionRunResponse:
        endpoint = self._get_function_run_endpoint(function_id, run_id).with_params(PayloadMode())
        return GetFunctionRunResponse.model_validate(resolve_run_fields(self._request(endpoint)))

    def update_run(
        self, function_id: str, run_id: str, **data: Unpack[FunctionRunUpdateRequestDict]
    ) -> UpdateFunctionRunResponse:
        request = FunctionRunUpdateRequest.model_validate(data)
        endpoint = self._update_function_run_endpoint(function_id, run_id)
        fields = request.model_dump(mode="json", exclude_unset=True)
        body = offload_run_fields(self, endpoint.path, fields)
        return self.request(endpoint.with_request(RunUpdateBody(body)))

    def list_runs(self, function_id: str, **data: Unpack[ListFunctionRunsRequestDict]) -> ListFunctionRunsResponse:
        """
        List all function runs.

        Use `list_runs(only_active=False)` to retrieve all runs, including completed ones.
        """
        request = ListFunctionRunsRequest.model_validate(data)
        return self.request(self._list_function_runs_endpoint(function_id).with_params(request))

    @staticmethod
    def decode_message(text: str):
        # Convert ANSI color codes to loguru color tags
        colored_text = FunctionsClient._ansi_to_loguru_colors(text)

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
            runtime=_request.runtime,
        )
        endpoint = self._start_function_run_endpoint(
            function_id=request.function_id, run_id=function_run_id
        ).with_request(request)

        headers = {"x-notte-api-key": self.token}
        headers["Content-Type"] = "application/json"
        headers = self.headers(headers=headers)
        url = self.request_path(endpoint)
        req_data = request.model_dump_json(exclude_none=True)
        timeout = timeout or self.FUNCTION_RUN_TIMEOUT

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
                        decoded = FunctionsClient.decode_message(log_msg)

                        if message["type"] == "log":
                            try:
                                logger.opt(colors=True).info(decoded)
                            except Exception:
                                logger.info(decoded)
                        elif message["type"] == "result":
                            result = log_msg
                        elif message["type"] == "session_start":
                            session_id = log_msg
                            try:
                                # Keep this optional lookup from using the normal 60-second request timeout.
                                status_endpoint = SessionsClient._session_status_endpoint(  # pyright: ignore[reportPrivateUsage]
                                    session_id=session_id
                                )
                                viewer_url = self.root_client.sessions.request(status_endpoint, timeout=2).viewer_url
                            except Exception:
                                # Viewer discovery is optional; errors may also contain credentials.
                                viewer_url = None
                            if viewer_url and self.token not in viewer_url:
                                logger.info(f"Live viewer for session available at: {viewer_url}")
                            else:
                                logger.info(
                                    f"Session {session_id} started. View it with client.sessions.viewer({session_id!r})."
                                )

                except json.JSONDecodeError:
                    continue

        if result is INITIAL:
            raise ValueError("Did not get any result from function run")

        return FunctionRunResponse.model_validate_json(result)

    def get_curl(self, function_id: str, **variables: Any) -> str:
        endpoint = self._start_function_run_endpoint_without_run_id(function_id=function_id)
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


class NotteFunction:
    """
    Notte function that runs on the Notte cloud.

    Functions are saved in the notte console for easy access and versioning for users.
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
        if _client is None:
            raise ValueError("NotteClient is required")
        # init attributes
        self.client: FunctionsClient = _client.functions
        self.root_client: NotteClient = _client
        self._response: GetFunctionResponse | GetFunctionWithLinkResponse | None = None
        if function_id is None:
            data["path"] = self._validate_path(data.get("path"))
            self._response = _client.functions.create(**data)
            function_id = self._response.function_id
            logger.info(f"[Function] {function_id} created successfully.")
        self._function_id: str = function_id
        self._session_id: str | None = None
        self._function_run_id: str | None = None
        self.decryption_key: str | None = decryption_key

    @staticmethod
    def _validate_path(path: str | None) -> str:
        if path is None:
            raise ValueError("'path' must be provided")
        if not path.endswith(".py"):
            raise ValueError(f"Code file path must end with .py, got '{path}'")
        return path

    @property
    def response(self) -> GetFunctionResponse | GetFunctionWithLinkResponse:
        if self._response is not None:
            return self._response
        self._response = self.client.get(function_id=self._function_id)
        logger.info(f"[Function] {self._response.function_id} metadata retrieved successfully.")
        return self._response

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

    @property
    def function_id(self) -> str:
        return self.response.function_id

    def replay(
        self,
        wait: bool = True,
        timeout: float = 120.0,
        poll_interval: float = 2.0,
    ) -> ReplayResponse:
        """
        Get presigned URLs for the function run replay.

        ```python
        function = notte.Function("<your-function-id>")
        function.run()
        replay = function.replay()
        print(replay.mp4_url)  # Presigned URL for MP4 download
        replay.download("function.mp4")
        ```

        Args:
            wait: If True (default), poll until the replay is ready.
            timeout: Maximum seconds to wait (default 120).
            poll_interval: Seconds between polling attempts (default 2).
        """
        if self._function_run_id is None:
            raise ValueError("You should call `run` before calling `replay`")
        if self._session_id is None:
            raise ValueError(
                f"Session ID not found in your function run {self._function_run_id}. Please check that your function is creating at least one `client.Session` in the `run` function."
            )
        return self.root_client.sessions.replay(
            session_id=self._session_id,
            wait=wait,
            timeout=timeout,
            poll_interval=poll_interval,
        )

    def update(self, path: str, version: str | None = None, restricted: bool = True) -> None:
        """
        Update the function with a new code version.

        ```python
        function = notte.Function("<your-function-id>")
        function.update(path="<path-to-your-function.py>")
        ```

        If you set a version, only that version will be updated. `restricted` controls how
        strictly the uploaded code is validated by the Notte API.
        """
        path = self._validate_path(path)
        self._response = self.client.update(
            function_id=self.response.function_id, path=path, version=version, restricted=restricted
        )
        logger.info(
            f"[Function] {self.response.function_id} updated successfully to version {self.response.latest_version}."
        )

    def delete(self) -> None:
        """
        Delete the function from the notte console.

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
            # cryptography is only needed for encrypted functions, so import it lazily
            from notte_sdk._encryption import Encryption

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
        path: str | None = None,
        version: str | None = None,
        decryption_key: str | None = None,
    ) -> str:
        """
        Download the function code from the notte console as a python file.

        ```python
        function = notte.Function("<your-function-id>")
        function.download(path="<path-to-your-function.py>", decryption_key="<your-key>")
        ```

        """
        final_path = None if path is None else self._validate_path(path)

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

    def create_run(self) -> CreateFunctionRunResponse:
        """
        Create a run record without starting execution.

        Returns the run ID before execution begins. Pass it explicitly to
        `run(function_run_id=...)` to execute this run; `run()` without an ID
        creates a new run.

        ```python
        function = notte.Function("<your-function-id>")
        created = function.create_run()
        result = function.run(function_run_id=created.function_run_id, url="https://example.com")
        ```

        `run()` still waits for completion. Creating a run does not launch a
        background job or change which run `run()` uses by default.
        """
        return self.client.create_run(self._function_id)

    def run(
        self,
        version: str | None = None,
        timeout: int | None = None,
        stream: bool = True,
        raise_on_failure: bool = True,
        function_run_id: str | None = None,
        runtime: FunctionRuntime | None = None,
        input_variables: dict[str, Any] | None = None,
        **variables: Any,
    ) -> FunctionRunResponse:
        """
        Run the function on the Notte cloud using the specified variables.

        This call waits for completion; streaming controls live log delivery.
        Optionally call `create_run()` only if you need the run ID before
        execution, then pass it as `function_run_id`. When `function_run_id`
        is omitted, `run()` automatically creates a new run.
        Omit runtime to use the saved function default. Pass runtime="extended"
        for longer cloud execution, or runtime="standard" to override that default.
        Use `input_variables={"runtime": value}` for script inputs whose names match
        SDK options; these are merged with keyword inputs, rejecting duplicates.

        ```python
        function = notte.Function("<your-function-id>")
        function.run(variable1="value1", variable2="value2")
        ```

        > Make sure that the correct variables are provided based on the python file previously uploaded. Otherwise, the function will fail.
        """
        runtime = TypeAdapter[FunctionRuntime | None](FunctionRuntime | None).validate_python(runtime)
        if input_variables is not None:
            if duplicates := input_variables.keys() & variables.keys():
                raise ValueError(f"Duplicate input variables: {sorted(duplicates)}")
            variables = {**input_variables, **variables}
        if version is not None:
            raise ValueError(
                "Running a specific version is not supported by the Notte cloud; update the function instead"
            )
        # first create the run on DB
        if function_run_id is None:
            function_run_id = self.client.create_run(self.function_id).function_run_id

        self._function_run_id = function_run_id
        logger.info(
            f"[Function Run] {function_run_id} created and scheduled for cloud execution with raise_on_failure={raise_on_failure}."
        )
        res = self.client.run(
            function_id=self.response.function_id,
            function_run_id=function_run_id,
            stream=stream,
            runtime=runtime,
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
        Convert the function run to a curl request.

        """
        return self.client.get_curl(function_id=self.function_id, **variables)
