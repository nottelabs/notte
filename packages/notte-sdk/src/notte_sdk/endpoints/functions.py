from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, ClassVar, Unpack, cast, final, overload

from notte_core.errors import NotteBaseError
from notte_core.logging import logger
from notte_core.telemetry import track_usage
from notte_core.types import (
    CreateFunctionRunRequest,
    CreateFunctionRunResponse,
    FunctionRunResponse,
    FunctionRuntime,
    ReplayResponse,
    RunFunctionRequestDict,
)
from typing_extensions import override

from notte_sdk._generated import operations as api
from notte_sdk._generated.public import (
    CreateFunctionRequestDict,
    FunctionRunGetMetadataParametersQueryDict,
    FunctionRunUpdateRequestDict,
    GetFunctionResponse,
    GetFunctionRunResponse,
    GetFunctionWithLinkResponse,
    UpdateFunctionRequestDict,
    UpdateFunctionRunResponse,
)
from notte_sdk._generated.resources import FunctionsOperations
from notte_sdk._requests import wire_request
from notte_sdk._transport import TransportError, get_text
from notte_sdk.endpoints.base import NotteEndpoint
from notte_sdk.endpoints.run_payloads import RunUpdateBody, offload_run_fields, resolve_run_fields

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
class FunctionsClient(FunctionsOperations):
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

    # Legacy: create and start-by-run-id are absent from the committed spec.
    # Streaming and multipart transfers remain hand-written.
    CREATE_FUNCTION_RUN = "{function_id}/runs/create"
    START_FUNCTION_RUN_WITHOUT_RUN_ID = "{function_id}/runs/start"
    STOP_FUNCTION_RUN = "{function_id}/runs/{run_id}"
    START_FUNCTION_RUN = "{function_id}/runs/{run_id}"
    GET_FUNCTION_RUN = "{function_id}/runs/{run_id}"
    LIST_FUNCTION_RUNS = "{function_id}/runs/"
    UPDATE_FUNCTION_RUN = "{function_id}/runs/{run_id}"
    RUN_FUNCTION_ENDPOINT = "{function_id}/runs/{run_id}"

    FUNCTION_RUN_TIMEOUT: ClassVar[int] = 60 * 5  # 5 minutes

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
    def _start_function_run_endpoint(function_id: str, run_id: str) -> NotteEndpoint[FunctionRunResponse]:
        """
        Returns a NotteEndpoint configured for starting a new function run.
        """
        return NotteEndpoint(
            path=FunctionsClient.START_FUNCTION_RUN.format(function_id=function_id, run_id=run_id),
            response=FunctionRunResponse,
            method="POST",
        )

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
        # `restricted` defaults to true server-side, so it is only sent to lift the restriction.
        query: dict[str, Any] = {} if restricted else {"restricted": False}
        if (version := data.get("version")) is not None:
            query["version"] = version
        endpoint = api.function_update(function_id, wire_request(None, {}), params=wire_request(None, query))
        return self.request_upload(endpoint, {"file": data["path"]})

    def create_run(self, function_id: str) -> CreateFunctionRunResponse:
        request = CreateFunctionRunRequest()
        return self.request(self._create_function_run_endpoint(function_id).with_request(request))

    @override
    def run_get_metadata(
        self, function_id: str, run_id: str, **data: Unpack[FunctionRunGetMetadataParametersQueryDict]
    ) -> GetFunctionRunResponse:
        _ = data.setdefault("payload_mode", "references")
        endpoint = api.function_run_get_metadata(function_id, run_id, params=wire_request(None, data))
        return GetFunctionRunResponse.model_validate(resolve_run_fields(self._request(endpoint)))

    @override
    def run_update_metadata(
        self, function_id: str, run_id: str, **data: Unpack[FunctionRunUpdateRequestDict]
    ) -> UpdateFunctionRunResponse:
        fields = wire_request(None, data).model_dump(mode="json")
        body = offload_run_fields(self, function_id, run_id, fields)
        return self.request(api.function_run_update_metadata(function_id, run_id, RunUpdateBody(body)))

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

    def run_start(
        self, function_run_id: str, timeout: int | None = None, **data: Unpack[RunFunctionRequestDict]
    ) -> FunctionRunResponse:
        # Reversible SDK normalization: legacy workflow spelling wins, as in AliasChoices.
        function_id = cast(str, data.get("workflow_id", data.get("function_id")))
        stream = data.get("stream", True)
        values = {
            "workflow_id": function_id,
            "workflow_run_id": function_run_id,
            "variables": data.get("variables"),
            "stream": stream,
            "runtime": data.get("runtime"),
        }
        request = wire_request(None, {key: value for key, value in values.items() if value is not None})
        endpoint = self._start_function_run_endpoint(function_id=function_id, run_id=function_run_id).with_request(
            request
        )
        # The runtime receives the caller's key in this header (Authorization is not forwarded).
        headers = {"x-notte-api-key": self.token}
        timeout = timeout or self.FUNCTION_RUN_TIMEOUT

        if not stream:
            return FunctionRunResponse.model_validate(self.request_once(endpoint, headers=headers, timeout=timeout))

        INITIAL = object()
        result: Any = INITIAL

        session_id = None
        with self.stream_lines(endpoint, headers=headers, timeout=timeout) as lines:
            for utf in lines:
                try:
                    # Lambda streaming often uses Server-Sent Events format
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
                                status_endpoint = api.session_status(session_id=session_id)
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
        endpoint = api.function_run_start(function_id, wire_request(None, {}))
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
        self._response = self.client.download_url(function_id=self._function_id)
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
            self._response = self.client.download_url(function_id=self.response.function_id, version=version)
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
            code_content = get_text(file_url, timeout=self.client.DEFAULT_REQUEST_TIMEOUT_SECONDS)
        except TransportError as e:
            raise ValueError(f"Failed to download function code from {file_url} in 30 seconds: {e}")

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
        res = self.client.run_start(
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
        return self.client.run_stop(function_id=self.function_id, run_id=run_id)

    def get_run(self, run_id: str) -> GetFunctionRunResponse:
        """
        Get a function run by its ID.

        """
        return self.client.run_get_metadata(function_id=self.function_id, run_id=run_id)

    def get_curl(self, **variables: Any) -> str:
        """
        Convert the function run to a curl request.

        """
        return self.client.get_curl(function_id=self.function_id, **variables)
