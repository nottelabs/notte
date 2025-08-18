from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Unpack, final, overload

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
    DeleteWorkflowRequest,
    DeleteWorkflowRequestDict,
    DeleteWorkflowResponse,
    GetWorkflowRequest,
    GetWorkflowRequestDict,
    GetWorkflowResponse,
    GetWorkflowWithLinkResponse,
    ListWorkflowsRequest,
    ListWorkflowsRequestDict,
    ListWorkflowsResponse,
    UpdateWorkflowRequest,
    UpdateWorkflowRequestDict,
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
    CREATE_SCRIPT = ""
    UPDATE_SCRIPT = "{workflow_id}"
    GET_SCRIPT = "{workflow_id}"
    DELETE_SCRIPT = "{workflow_id}"
    LIST_SCRIPTS = ""

    @staticmethod
    def _create_workflow_endpoint() -> NotteEndpoint[GetWorkflowResponse]:
        """
        Returns a NotteEndpoint configured for creating a new workflow.

        Returns:
            A NotteEndpoint with the POST method that expects a GetWorkflowResponse.
        """
        return NotteEndpoint(
            path=WorkflowsClient.CREATE_SCRIPT,
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
            path=WorkflowsClient.UPDATE_SCRIPT.format(workflow_id=workflow_id),
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
            path=WorkflowsClient.GET_SCRIPT.format(workflow_id=workflow_id),
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
            path=WorkflowsClient.DELETE_SCRIPT.format(workflow_id=workflow_id),
            response=DeleteWorkflowResponse,
            method="DELETE",
        )

    @staticmethod
    def _list_workflows_endpoint() -> NotteEndpoint[ListWorkflowsResponse]:
        """
        Returns a NotteEndpoint configured for listing all workflows.

        Returns:
            A NotteEndpoint with the GET method that expects a ListWorkflowsResponse.
        """
        return NotteEndpoint(
            path=WorkflowsClient.LIST_SCRIPTS,
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
            WorkflowsClient._create_workflow_endpoint(),
            WorkflowsClient._update_workflow_endpoint(""),
            WorkflowsClient._get_workflow_endpoint(""),
            WorkflowsClient._delete_workflow_endpoint(""),
            WorkflowsClient._list_workflows_endpoint(),
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
    def update(self, **data: Unpack[UpdateWorkflowRequestDict]) -> GetWorkflowResponse:
        """
        Update an existing workflow.

        Args:
            workflow_id: The ID of the workflow to update.
            **data: Unpacked dictionary containing the workflow update parameters.

        Returns:
            GetWorkflowResponse: The updated workflow information.
        """
        request = UpdateWorkflowRequest.model_validate(data)
        endpoint = self._update_workflow_endpoint(request.workflow_id).with_file(request.workflow_path)
        if request.version is not None:
            endpoint = endpoint.with_params(
                GetWorkflowRequest(workflow_id=request.workflow_id, version=request.version)
            )
        response = self.request(endpoint)
        return response

    @track_usage("cloud.workflow.get")
    def get(self, **data: Unpack[GetWorkflowRequestDict]) -> GetWorkflowWithLinkResponse:
        """
        Get a workflow with download URL.

        Args:
            workflow_id: The ID of the workflow to get.
            **data: Unpacked dictionary containing parameters for the request.

        Returns:
            GetWorkflowWithLinkResponse: Response containing the workflow information and download URL.
        """
        params = GetWorkflowRequest.model_validate(data)
        response = self.request(self._get_workflow_endpoint(params.workflow_id).with_params(params))
        return response

    @track_usage("cloud.workflow.delete")
    def delete(self, **data: Unpack[DeleteWorkflowRequestDict]) -> DeleteWorkflowResponse:
        """
        Delete a workflow.

        Args:
            workflow_id: The ID of the workflow to delete.
            **data: Unpacked dictionary containing parameters for the request.
        """
        request = DeleteWorkflowRequest.model_validate(data)
        return self.request(self._delete_workflow_endpoint(request.workflow_id).with_params(request))

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


class RemoteWorkflow:
    def __init__(self, client: NotteClient, response: GetWorkflowResponse):
        self.client: WorkflowsClient = client.workflows
        self.root_client: NotteClient = client
        self.response: GetWorkflowResponse | GetWorkflowWithLinkResponse = response

    def run(self, version: str | None = None) -> BaseModel:
        code = self.download(workflow_path=None, version=version)
        return SecureScriptRunner(notte_module=self.root_client).run_script(code)  # pyright: ignore [reportArgumentType]

    def update(self, workflow_path: str, version: str | None = None) -> None:
        self.response = self.client.update(
            workflow_id=self.response.workflow_id, workflow_path=workflow_path, version=version
        )
        logger.info(
            f"[Workflow] {self.response.workflow_id} updated successfully to version {self.response.latest_version}."
        )

    def delete(self) -> None:
        _ = self.client.delete(workflow_id=self.response.workflow_id)
        logger.info(f"[Workflow] {self.response.workflow_id} deleted successfully.")

    def get_url(self, version: str | None = None) -> str:
        if not isinstance(self.response, GetWorkflowWithLinkResponse) or version != self.response.latest_version:
            self.response = self.client.get(workflow_id=self.response.workflow_id, version=version)
        return self.response.url

    def download(self, workflow_path: str | None, version: str | None = None) -> str:
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
