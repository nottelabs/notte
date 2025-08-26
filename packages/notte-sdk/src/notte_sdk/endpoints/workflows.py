from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Unpack, final, overload

import requests
from loguru import logger
from notte_core.ast import SecureScriptRunner
from notte_core.common.telemetry import track_usage
from pydantic import BaseModel
from typing_extensions import override

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

if TYPE_CHECKING:
    from notte_sdk.client import NotteClient


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
    START_WORKFLOW_RUN = "{workflow_id}/runs/{run_id}"
    GET_WORKFLOW_RUN = "{workflow_id}/runs/{run_id}"
    LIST_WORKFLOW_RUNS = "{workflow_id}/runs"
    UPDATE_WORKFLOW_RUN = "{workflow_id}/runs/{run_id}"
    RUN_WORKFLOW_ENDPOINT = "{workflow_id}/runs/{run_id}"

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
            method="POST",
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

    @override
    @staticmethod
    def endpoints() -> Sequence[NotteEndpoint[BaseModel]]:
        """Returns the available workflow endpoints.

        Aggregates endpoints from WorkflowsClient for creating, updating, getting, and listing workflows."""
        return [
            # workflow management endpoints
            WorkflowsClient._create_workflow_endpoint(),
            WorkflowsClient._update_workflow_endpoint(""),
            WorkflowsClient._get_workflow_endpoint(""),
            WorkflowsClient._delete_workflow_endpoint(""),
            WorkflowsClient._list_workflows_endpoint(),
            # run endpoints
            WorkflowsClient._create_workflow_run_endpoint(""),
            WorkflowsClient._start_workflow_run_endpoint("", ""),
            WorkflowsClient._get_workflow_run_endpoint("", ""),
            WorkflowsClient._list_workflow_runs_endpoint(""),
            WorkflowsClient._update_workflow_run_endpoint("", ""),
        ]

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
        response = self.request(self._list_workflows_endpoint().with_params(params))
        return response

    def create_run(self, workflow_id: str) -> CreateWorkflowRunResponse:
        request = CreateWorkflowRunRequest(workflow_id=workflow_id)
        response = self.request(self._create_workflow_run_endpoint(workflow_id).with_request(request))
        return response

    def update_run(
        self, workflow_id: str, run_id: str, **data: Unpack[WorkflowRunUpdateRequestDict]
    ) -> UpdateWorkflowRunResponse:
        request = WorkflowRunUpdateRequest.model_validate(data)
        response = self.request(self._update_workflow_run_endpoint(workflow_id, run_id).with_request(request))
        return response

    def list_runs(self, workflow_id: str, **data: Unpack[ListWorkflowRunsRequestDict]) -> ListWorkflowRunsResponse:
        request = ListWorkflowRunsRequest.model_validate(data)
        response = self.request(self._list_workflow_runs_endpoint(workflow_id).with_params(request))
        return response

    def run(self, workflow_run_id: str, **data: Unpack[RunWorkflowRequestDict]) -> WorkflowRunResponse:
        req = RunWorkflowRequest.model_validate(data)
        body = StartWorkflowRunRequest(
            workflow_id=req.workflow_id,
            workflow_run_id=workflow_run_id,
            variables=req.variables,
        ).model_dump()
        response = requests.post(
            url=self.RUN_WORKFLOW_ENDPOINT.format(workflow_id=req.workflow_id, run_id=workflow_run_id),
            json=body,
            headers={"x-notte-api-key": self.token},
        )
        response.raise_for_status()
        data = response.json()
        res = WorkflowRunResponse.model_validate(data)
        return res


class RemoteWorkflow:
    """
    Notte workflow that can be run on the cloud or locally.

    Workflows are saved in the notte console for easy access and versioning for users.
    """

    def __init__(self, client: NotteClient, response: GetWorkflowResponse):
        self.client: WorkflowsClient = client.workflows
        self.root_client: NotteClient = client
        self.response: GetWorkflowResponse | GetWorkflowWithLinkResponse = response

    @property
    def workflow_id(self) -> str:
        return self.response.workflow_id

    def run(
        self, version: str | None = None, local: bool = False, strict: bool = True, **variables: Any
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
        create_run_response = self.client.create_run(self.workflow_id)
        logger.info(
            f"[Workflow] Workflow {self.workflow_id} run created with id {create_run_response.workflow_run_id}."
        )
        if local:
            code = self.download(workflow_path=None, version=version)
            result = SecureScriptRunner(notte_module=self.root_client).run_script(  # pyright: ignore [reportArgumentType]
                code, variables=variables, strict=strict
            )
            # update the run with the result
            _ = self.client.update_run(self.workflow_id, create_run_response.workflow_run_id, result=result)
            return result
        # run on cloud
        return self.client.run(
            workflow_id=self.response.workflow_id,
            workflow_run_id=create_run_response.workflow_run_id,
            variables=variables,
        )

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
        return self.response.url

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


@final
class RemoteWorkflowFactory:
    def __init__(self, client: NotteClient):
        self.client = client.workflows
        self.root_client = client

    @overload
    def __call__(self, /, workflow_id: str) -> RemoteWorkflow: ...

    @overload
    def __call__(self, **data: Unpack[CreateWorkflowRequestDict]) -> RemoteWorkflow: ...

    def __call__(self, workflow_id: str | None = None, **data: Unpack[CreateWorkflowRequestDict]) -> RemoteWorkflow:  # pyright: ignore[reportInconsistentOverload]
        if workflow_id is None:
            response = self.client.create(**data)
            logger.info(f"[Workflow] {response.workflow_id} created successfully.")
        else:
            response = self.client.get(workflow_id=workflow_id)
            logger.info(f"[Workflow] {response.workflow_id} retrieved successfully.")
        return RemoteWorkflow(self.root_client, response)
