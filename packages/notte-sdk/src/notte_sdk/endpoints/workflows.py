from __future__ import annotations

import json
import traceback
from typing import TYPE_CHECKING, Any, ClassVar, Unpack, final, overload

import requests
from loguru import logger
from notte_core.ast import SecureScriptRunner
from notte_core.common.telemetry import track_usage
from notte_core.errors.base import NotteBaseError
from notte_core.utils.encryption import Encryption
from notte_core.utils.webp_replay import WebpReplay

from notte_sdk.endpoints.base import BaseClient, NotteEndpoint
from notte_sdk.types import (
    CreateWorkflowRequest,
    CreateWorkflowRequestDict,
    CreateWorkflowRunRequest,
    CreateWorkflowRunResponse,
    DeleteWorkflowResponse,
    GetWorkflowRequest,
    GetWorkflowRequestDict,
    GetWorkflowResponse,
    GetWorkflowRunResponse,
    GetWorkflowWithLinkResponse,
    ListWorkflowRunsRequest,
    ListWorkflowRunsRequestDict,
    ListWorkflowRunsResponse,
    ListWorkflowsRequest,
    ListWorkflowsRequestDict,
    ListWorkflowsResponse,
    RunWorkflowRequest,
    RunWorkflowRequestDict,
    StartWorkflowRunRequest,
    UpdateWorkflowRequest,
    UpdateWorkflowRequestDict,
    UpdateWorkflowRunResponse,
    WorkflowRunResponse,
    WorkflowRunUpdateRequest,
    WorkflowRunUpdateRequestDict,
)
from notte_sdk.utils import LogCapture

if TYPE_CHECKING:
    from notte_sdk.client import NotteClient


@final
class FailedToRunCloudWorkflowError(NotteBaseError):
    """
    Exception raised when a workflow run fails to run on the cloud.
    """

    def __init__(self, workflow_id: str, workflow_run_id: str, response: WorkflowRunResponse):
        self.message = f"Workflow {workflow_id} with run_id={workflow_run_id} failed with result '{response.result}'"
        self.workflow_id = workflow_id
        self.workflow_run_id = workflow_run_id
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
    UPDATE_WORKFLOW = "{workflow_id}"
    GET_WORKFLOW = "{workflow_id}"
    DELETE_WORKFLOW = "{workflow_id}"
    LIST_WORKFLOWS = ""

    # RUN endpoints ...
    CREATE_WORKFLOW_RUN = "{workflow_id}/runs/create"
    START_WORKFLOW_RUN_WITHOUT_RUN_ID = "{workflow_id}/runs/start"
    START_WORKFLOW_RUN = "{workflow_id}/runs/{run_id}"
    GET_WORKFLOW_RUN = "{workflow_id}/runs/{run_id}"
    LIST_WORKFLOW_RUNS = "{workflow_id}/runs/"
    UPDATE_WORKFLOW_RUN = "{workflow_id}/runs/{run_id}"
    RUN_WORKFLOW_ENDPOINT = "{workflow_id}/runs/{run_id}"

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
    def _create_workflow_endpoint() -> NotteEndpoint[GetWorkflowResponse]:
        """
        Returns a NotteEndpoint configured for creating a new workflow.

        Returns:
            A NotteEndpoint with the POST method that expects a GetWorkflowResponse.
        """
        return NotteEndpoint(
            path=WorkflowsClient.CREATE_WORKFLOW,
            response=GetWorkflowResponse,
            method="POST",
        )

    @staticmethod
    def _update_workflow_endpoint(workflow_id: str) -> NotteEndpoint[GetWorkflowResponse]:
        """
        Returns a NotteEndpoint configured for updating a workflow.

        Args:
            workflow_id: The ID of the workflow to update.

        Returns:
            A NotteEndpoint with the POST method that expects a GetWorkflowResponse.
        """
        return NotteEndpoint(
            path=WorkflowsClient.UPDATE_WORKFLOW.format(workflow_id=workflow_id),
            response=GetWorkflowResponse,
            method="POST",
        )

    @staticmethod
    def _get_workflow_endpoint(workflow_id: str) -> NotteEndpoint[GetWorkflowWithLinkResponse]:
        """
        Returns a NotteEndpoint configured for getting a workflow with download URL.

        Args:
            workflow_id: The ID of the workflow to get.

        Returns:
            A NotteEndpoint with the GET method that expects a GetWorkflowWithLinkResponse.
        """
        return NotteEndpoint(
            path=WorkflowsClient.GET_WORKFLOW.format(workflow_id=workflow_id),
            response=GetWorkflowWithLinkResponse,
            method="GET",
        )

    @staticmethod
    def _delete_workflow_endpoint(workflow_id: str) -> NotteEndpoint[DeleteWorkflowResponse]:
        """
        Returns a NotteEndpoint configured for deleting a workflow.

        Args:
            workflow_id: The ID of the workflow to delete.

        Returns:
            A NotteEndpoint with the DELETE method.
        """
        return NotteEndpoint(
            path=WorkflowsClient.DELETE_WORKFLOW.format(workflow_id=workflow_id),
            response=DeleteWorkflowResponse,
            method="DELETE",
        )

    @staticmethod
    def _create_workflow_run_endpoint(workflow_id: str) -> NotteEndpoint[CreateWorkflowRunResponse]:
        """
        Returns a NotteEndpoint configured for creating a new workflow run.
        """
        return NotteEndpoint(
            path=WorkflowsClient.CREATE_WORKFLOW_RUN.format(workflow_id=workflow_id),
            response=CreateWorkflowRunResponse,
            method="POST",
        )

    @staticmethod
    def _start_workflow_run_endpoint(workflow_id: str, run_id: str) -> NotteEndpoint[WorkflowRunResponse]:
        """
        Returns a NotteEndpoint configured for starting a new workflow run.
        """
        return NotteEndpoint(
            path=WorkflowsClient.START_WORKFLOW_RUN.format(workflow_id=workflow_id, run_id=run_id),
            response=WorkflowRunResponse,
            method="POST",
        )

    @staticmethod
    def _start_workflow_run_endpoint_without_run_id(workflow_id: str) -> NotteEndpoint[WorkflowRunResponse]:
        """
        Returns a NotteEndpoint configured for starting a new workflow run.
        """
        return NotteEndpoint(
            path=WorkflowsClient.START_WORKFLOW_RUN_WITHOUT_RUN_ID.format(workflow_id=workflow_id),
            response=WorkflowRunResponse,
            method="POST",
        )

    @staticmethod
    def _get_workflow_run_endpoint(workflow_id: str, run_id: str) -> NotteEndpoint[GetWorkflowRunResponse]:
        """
        Returns a NotteEndpoint configured for getting a workflow run.
        """
        return NotteEndpoint(
            path=WorkflowsClient.GET_WORKFLOW_RUN.format(workflow_id=workflow_id, run_id=run_id),
            response=GetWorkflowRunResponse,
            method="GET",
        )

    @staticmethod
    def _list_workflow_runs_endpoint(workflow_id: str) -> NotteEndpoint[ListWorkflowRunsResponse]:
        """
        Returns a NotteEndpoint configured for listing all workflow runs.
        """
        return NotteEndpoint(
            path=WorkflowsClient.LIST_WORKFLOW_RUNS.format(workflow_id=workflow_id),
            response=ListWorkflowRunsResponse,
            method="GET",
        )

    @staticmethod
    def _update_workflow_run_endpoint(workflow_id: str, run_id: str) -> NotteEndpoint[UpdateWorkflowRunResponse]:
        """
        Returns a NotteEndpoint configured for updating a workflow run.
        """
        return NotteEndpoint(
            path=WorkflowsClient.UPDATE_WORKFLOW_RUN.format(workflow_id=workflow_id, run_id=run_id),
            response=UpdateWorkflowRunResponse,
            method="PATCH",
        )

    @staticmethod
    def _list_workflows_endpoint() -> NotteEndpoint[ListWorkflowsResponse]:
        """
        Returns a NotteEndpoint configured for listing all workflows.

        Returns:
            A NotteEndpoint with the GET method that expects a ListWorkflowsResponse.
        """
        return NotteEndpoint(
            path=WorkflowsClient.LIST_WORKFLOWS,
            response=ListWorkflowsResponse,
            method="GET",
        )

    @track_usage("cloud.workflow.create")
    def create(self, **data: Unpack[CreateWorkflowRequestDict]) -> GetWorkflowResponse:
        """
        Create a new workflow.

        Args:
            **data: Unpacked dictionary containing the workflow creation parameters.

        Returns:
            GetWorkflowResponse: The created workflow information.
        """
        request = CreateWorkflowRequest.model_validate(data)
        endpoint = self._create_workflow_endpoint().with_file(request.workflow_path)
        response = self.request(endpoint)
        return response

    @track_usage("cloud.workflow.update")
    def update(self, workflow_id: str, **data: Unpack[UpdateWorkflowRequestDict]) -> GetWorkflowResponse:
        """
        Update an existing workflow.

        Args:
            workflow_id: The ID of the workflow to update.
            **data: Unpacked dictionary containing the workflow update parameters.

        Returns:
            GetWorkflowResponse: The updated workflow information.
        """
        request = UpdateWorkflowRequest.model_validate(data)
        endpoint = self._update_workflow_endpoint(workflow_id).with_file(request.workflow_path)
        if request.version is not None:
            endpoint = endpoint.with_params(GetWorkflowRequest(version=request.version))
        response = self.request(endpoint)
        return response

    @track_usage("cloud.workflow.get")
    def get(self, workflow_id: str, **data: Unpack[GetWorkflowRequestDict]) -> GetWorkflowWithLinkResponse:
        """
        Get a workflow with download URL.

        Args:
            workflow_id: The ID of the workflow to get.
            **data: Unpacked dictionary containing parameters for the request.

        Returns:
            GetWorkflowWithLinkResponse: Response containing the workflow information and download URL.
        """
        params = GetWorkflowRequest.model_validate(data)
        response = self.request(self._get_workflow_endpoint(workflow_id).with_params(params))
        return response

    @track_usage("cloud.workflow.delete")
    def delete(self, workflow_id: str) -> DeleteWorkflowResponse:
        """
        Delete a workflow.

        Args:
            workflow_id: The ID of the workflow to delete.
        """
        return self.request(self._delete_workflow_endpoint(workflow_id))

    @track_usage("cloud.workflow.list")
    def list(self, **data: Unpack[ListWorkflowsRequestDict]) -> ListWorkflowsResponse:
        """
        List all available workflows.

        Args:
            **data: Unpacked dictionary containing parameters for the request.

        Returns:
            ListWorkflowsResponse: Response containing the list of workflows.
        """
        params = ListWorkflowsRequest.model_validate(data)
        return self.request(self._list_workflows_endpoint().with_params(params))

    def create_run(self, workflow_id: str) -> CreateWorkflowRunResponse:
        request = CreateWorkflowRunRequest(workflow_id=workflow_id)
        return self.request(self._create_workflow_run_endpoint(workflow_id).with_request(request))

    def get_run(self, workflow_id: str, run_id: str) -> GetWorkflowRunResponse:
        return self.request(self._get_workflow_run_endpoint(workflow_id, run_id))

    def update_run(
        self, workflow_id: str, run_id: str, **data: Unpack[WorkflowRunUpdateRequestDict]
    ) -> UpdateWorkflowRunResponse:
        request = WorkflowRunUpdateRequest.model_validate(data)
        return self.request(self._update_workflow_run_endpoint(workflow_id, run_id).with_request(request))

    def list_runs(self, workflow_id: str, **data: Unpack[ListWorkflowRunsRequestDict]) -> ListWorkflowRunsResponse:
        """
        List all workflow runs.

        Use `list_runs(only_active=False)` to retrieve all runs, including completed ones.
        """
        request = ListWorkflowRunsRequest.model_validate(data)
        return self.request(self._list_workflow_runs_endpoint(workflow_id).with_params(request))

    def run(
        self, workflow_run_id: str, timeout: int | None = None, **data: Unpack[RunWorkflowRequestDict]
    ) -> WorkflowRunResponse:
        _request = RunWorkflowRequest.model_validate(data)
        request = StartWorkflowRunRequest(
            workflow_id=_request.workflow_id,
            workflow_run_id=workflow_run_id,
            variables=_request.variables,
        )
        endpoint = self._start_workflow_run_endpoint(
            workflow_id=request.workflow_id, run_id=workflow_run_id
        ).with_request(request)
        return self.request(
            endpoint, headers={"x-notte-api-key": self.token}, timeout=timeout or self.WORKFLOW_RUN_TIMEOUT
        )

    def get_curl(self, workflow_id: str, **variables: Any) -> str:
        endpoint = self._start_workflow_run_endpoint_without_run_id(workflow_id=workflow_id)
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
    "workflow_id": "{workflow_id}",
    "variables": {indented_variables}
}}'
"""


class RemoteWorkflow:
    """
    Notte workflow that can be run on the cloud or locally.

    Workflows are saved in the notte console for easy access and versioning for users.
    """

    @overload
    def __init__(
        self, /, workflow_id: str, *, decryption_key: str | None = None, _client: NotteClient | None = None
    ) -> None: ...

    @overload
    def __init__(self, *, _client: NotteClient | None = None, **data: Unpack[CreateWorkflowRequestDict]) -> None: ...

    def __init__(  # pyright: ignore[reportInconsistentOverload]
        self,
        workflow_id: str | None = None,
        *,
        decryption_key: str | None = None,
        _client: NotteClient | None = None,
        **data: Unpack[CreateWorkflowRequestDict],
    ) -> None:
        if _client is None:
            raise ValueError("NotteClient is required")
        if workflow_id is None:
            response = _client.workflows.create(**data)
            logger.info(f"[Workflow] {response.workflow_id} created successfully.")
        else:
            response = _client.workflows.get(workflow_id=workflow_id)
            logger.info(f"[Workflow] {response.workflow_id} retrieved successfully.")
        # init attributes
        self.client: WorkflowsClient = _client.workflows
        self.root_client: NotteClient = _client
        self.response: GetWorkflowResponse | GetWorkflowWithLinkResponse = response
        self._session_id: str | None = None
        self._workflow_run_id: str | None = None
        self.decryption_key: str | None = decryption_key

    @property
    def workflow_id(self) -> str:
        return self.response.workflow_id

    def replay(self) -> WebpReplay:
        """
        Replay the workflow run.

        ```python
        workflow = notte.Workflow("<your-workflow-id>")
        workflow.run()
        replay = workflow.replay()
        replay.save("workflow_replay.webp")
        ```
        """
        if self._workflow_run_id is None:
            raise ValueError(
                "You should call `run` before calling `replay` (only available for remote workflow executions)"
            )
        if self._session_id is None:
            raise ValueError(
                f"Session ID not found in your workflow run {self._workflow_run_id}. Please check that your workflow is creating at least one `client.Session` in the `run` function."
            )
        return self.root_client.sessions.replay(session_id=self._session_id)

    def update(self, workflow_path: str, version: str | None = None) -> None:
        """
        Update the workflow with a a new code version.

        ```python
        workflow = notte.Workflow("<your-workflow-id>")
        workflow.update(workflow_path="<path-to-your-workflow.py>")
        ```

        If you set a version, only that version will be updated.
        """
        self.response = self.client.update(
            workflow_id=self.response.workflow_id, workflow_path=workflow_path, version=version
        )
        logger.info(
            f"[Workflow] {self.response.workflow_id} updated successfully to version {self.response.latest_version}."
        )

    def delete(self) -> None:
        """
        Delete the workflow from the notte console.

        ```python
        workflow = notte.Workflow("<your-workflow-id>")
        workflow.delete()
        ```
        """
        _ = self.client.delete(workflow_id=self.response.workflow_id)
        logger.info(f"[Workflow] {self.response.workflow_id} deleted successfully.")

    def get_url(self, version: str | None = None) -> str:
        if not isinstance(self.response, GetWorkflowWithLinkResponse) or version != self.response.latest_version:
            self.response = self.client.get(workflow_id=self.response.workflow_id, version=version)
        url = self.response.url
        decrypted: bool = url.startswith("https://") or url.startswith("http://")
        if not decrypted:
            if self.decryption_key is None:
                raise ValueError(
                    "Decryption key is required to decrypt the workflow download url. Set the `notte.Workflow(workflow_id='<your-workflow-id>', decryption_key='<your-key>')` when creating the workflow."
                )
            encryption = Encryption(root_key=self.decryption_key)
            url = encryption.decrypt(url)
            decrypted = url.startswith("https://") or url.startswith("http://")
            if not decrypted:
                raise ValueError(
                    f"Failed to decrypt workflow download url: {url}. Call support@notte.cc if you need help."
                )
            logger.info("🔐 Successfully decrypted workflow download url")
        return url

    def download(self, workflow_path: str | None, version: str | None = None) -> str:
        """
        Download the workflow code from the notte console as a python file.

        ```python
        workflow = notte.Workflow("<your-workflow-id>")
        workflow.download(workflow_path="<path-to-your-workflow.py>")
        ```

        """
        if workflow_path is not None and not workflow_path.endswith(".py"):
            raise ValueError(f"Workflow path must end with .py, got '{workflow_path}'")

        file_url = self.get_url(version=version)
        try:
            response = requests.get(file_url, timeout=30)
            response.raise_for_status()
        except requests.RequestException as e:
            raise ValueError(f"Failed to download workflow from {file_url} in 30 seconds: {e}")

        workflow_content = response.text
        if workflow_path is None:
            return workflow_content
        with open(workflow_path, "w") as f:
            _ = f.write(workflow_content)
        logger.info(f"[Workflow] {self.response.workflow_id} downloaded successfully to {workflow_path}.")
        return response.text

    def run(
        self,
        version: str | None = None,
        local: bool = False,
        restricted: bool = True,
        timeout: int | None = None,
        raise_on_failure: bool = True,
        workflow_run_id: str | None = None,
        **variables: Any,
    ) -> WorkflowRunResponse:
        """
        Run the workflow using the specified version and variables.

        If no version is provided, the latest version is used.

        ```python
        workflow = notte.Workflow("<your-workflow-id>")
        workflow.run(variable1="value1", variable2="value2", local=True)
        ```

        > Make sure that the correct variables are provided based on the python file previously uploaded. Otherwise, the workflow will fail.

        You can use `local=True` to run the workflow locally.

        """
        # first create the run on DB
        if workflow_run_id is None:
            create_run_response = self.client.create_run(self.workflow_id)
            workflow_run_id = create_run_response.workflow_run_id
        self._workflow_run_id = workflow_run_id
        logger.info(
            f"[Workflow Run] {workflow_run_id} created and scheduled for {'local' if local else 'cloud'} execution with raise_on_failure={raise_on_failure}."
        )
        if local:
            code = self.download(workflow_path=None, version=version)
            exception: Exception | None = None
            log_capture = LogCapture()
            try:
                with log_capture:
                    result = SecureScriptRunner(notte_module=self.root_client).run_script(  # pyright: ignore [reportArgumentType]
                        code, variables=variables, restricted=restricted
                    )
                    status = "closed"
            except Exception as e:
                logger.error(f"[Workflow] Workflow {self.workflow_id} run failed with error: {traceback.format_exc()}")
                result = str(e)
                status = "failed"
                exception = e
            # update the run with the result
            self._session_id = log_capture.session_id
            _ = self.client.update_run(
                workflow_id=self.workflow_id,
                run_id=workflow_run_id,
                result=str(result),
                variables=variables,
                status=status,
                session_id=log_capture.session_id,
                logs=log_capture.get_logs(),
            )
            if raise_on_failure and exception is not None:
                raise exception
            return WorkflowRunResponse(
                workflow_id=self.workflow_id,
                workflow_run_id=workflow_run_id,
                session_id=log_capture.session_id,
                result=result,
                status=status,
            )
        # run on cloud
        res = self.client.run(
            workflow_id=self.response.workflow_id,
            workflow_run_id=workflow_run_id,
            timeout=timeout,
            variables=variables,
        )
        if raise_on_failure and res.status == "failed":
            raise FailedToRunCloudWorkflowError(self.workflow_id, workflow_run_id, res)
        self._session_id = res.session_id
        return res

    def get_curl(self, **variables: Any) -> str:
        return self.client.get_curl(workflow_id=self.workflow_id, **variables)
