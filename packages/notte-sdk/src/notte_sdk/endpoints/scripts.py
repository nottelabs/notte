from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Unpack, final, overload

import requests
from loguru import logger
from notte_core.common.telemetry import track_usage
from pydantic import BaseModel
from typing_extensions import override

from notte_sdk.endpoints.base import BaseClient, NotteEndpoint
from notte_sdk.types import (
    CreateScriptRequestDict,
    DeleteScriptRequest,
    DeleteScriptRequestDict,
    GetScriptRequest,
    GetScriptRequestDict,
    GetScriptResponse,
    GetScriptWithLinkResponse,
    ListScriptsRequest,
    ListScriptsRequestDict,
    ListScriptsResponse,
    UpdateScriptRequest,
    UpdateScriptRequestDict,
)

if TYPE_CHECKING:
    from notte_sdk.client import NotteClient


@final
class ScriptsClient(BaseClient):
    """
    Client for the Notte Scripts API.

    Note: this client is only able to handle one session at a time.
    If you need to handle multiple sessions, you need to create a new client for each session.
    """

    # Script endpoints
    CREATE_SCRIPT = ""
    UPDATE_SCRIPT = "{script_id}"
    GET_SCRIPT = "{script_id}"
    DELETE_SCRIPT = "{script_id}"
    LIST_SCRIPTS = ""

    @staticmethod
    def _create_script_endpoint() -> NotteEndpoint[GetScriptResponse]:
        """
        Returns a NotteEndpoint configured for creating a new script.

        Returns:
            A NotteEndpoint with the POST method that expects a GetScriptResponse.
        """
        return NotteEndpoint(
            path=ScriptsClient.CREATE_SCRIPT,
            response=GetScriptResponse,
            method="POST",
        )

    @staticmethod
    def _update_script_endpoint(script_id: str) -> NotteEndpoint[GetScriptResponse]:
        """
        Returns a NotteEndpoint configured for updating a script.

        Args:
            script_id: The ID of the script to update.

        Returns:
            A NotteEndpoint with the POST method that expects a GetScriptResponse.
        """
        return NotteEndpoint(
            path=ScriptsClient.UPDATE_SCRIPT.format(script_id=script_id),
            response=GetScriptResponse,
            method="POST",
        )

    @staticmethod
    def _get_script_endpoint(script_id: str) -> NotteEndpoint[GetScriptWithLinkResponse]:
        """
        Returns a NotteEndpoint configured for getting a script with download URL.

        Args:
            script_id: The ID of the script to get.

        Returns:
            A NotteEndpoint with the GET method that expects a GetScriptWithLinkResponse.
        """
        return NotteEndpoint(
            path=ScriptsClient.GET_SCRIPT.format(script_id=script_id),
            response=GetScriptWithLinkResponse,
            method="GET",
        )

    @staticmethod
    def _delete_script_endpoint(script_id: str) -> NotteEndpoint[BaseModel]:
        """
        Returns a NotteEndpoint configured for deleting a script.

        Args:
            script_id: The ID of the script to delete.

        Returns:
            A NotteEndpoint with the DELETE method.
        """
        return NotteEndpoint(
            path=ScriptsClient.DELETE_SCRIPT.format(script_id=script_id),
            response=BaseModel,
            method="DELETE",
        )

    @staticmethod
    def _list_scripts_endpoint() -> NotteEndpoint[ListScriptsResponse]:
        """
        Returns a NotteEndpoint configured for listing all scripts.

        Returns:
            A NotteEndpoint with the GET method that expects a ListScriptsResponse.
        """
        return NotteEndpoint(
            path=ScriptsClient.LIST_SCRIPTS,
            response=ListScriptsResponse,
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
        Initialize a ScriptsClient instance.

        Initializes the client with an optional API key for script management.
        """
        super().__init__(
            root_client=root_client,
            base_endpoint_path="scripts",
            server_url=server_url,
            api_key=api_key,
            verbose=verbose,
        )

    @override
    @staticmethod
    def endpoints() -> Sequence[NotteEndpoint[BaseModel]]:
        """Returns the available script endpoints.

        Aggregates endpoints from ScriptsClient for creating, updating, getting, and listing scripts."""
        return [
            ScriptsClient._create_script_endpoint(),
            ScriptsClient._update_script_endpoint(""),
            ScriptsClient._get_script_endpoint(""),
            ScriptsClient._delete_script_endpoint(""),
            ScriptsClient._list_scripts_endpoint(),
        ]

    @track_usage("cloud.script.create")
    def create(self, **data: Unpack[CreateScriptRequestDict]) -> GetScriptResponse:
        """
        Create a new script.

        Args:
            **data: Unpacked dictionary containing the script creation parameters.

        Returns:
            GetScriptResponse: The created script information.
        """
        script_path = data["script_path"]
        endpoint = self._create_script_endpoint().with_file(script_path)
        response = self.request(endpoint)
        return response

    @track_usage("cloud.script.update")
    def update(self, **data: Unpack[UpdateScriptRequestDict]) -> GetScriptResponse:
        """
        Update an existing script.

        Args:
            script_id: The ID of the script to update.
            **data: Unpacked dictionary containing the script update parameters.

        Returns:
            GetScriptResponse: The updated script information.
        """
        request = UpdateScriptRequest.model_validate(data)
        endpoint = self._update_script_endpoint(request.script_id).with_file(request.script_path)
        response = self.request(endpoint)
        return response

    @track_usage("cloud.script.get")
    def get(self, **data: Unpack[GetScriptRequestDict]) -> GetScriptWithLinkResponse:
        """
        Get a script with download URL.

        Args:
            script_id: The ID of the script to get.
            **data: Unpacked dictionary containing parameters for the request.

        Returns:
            GetScriptWithLinkResponse: Response containing the script information and download URL.
        """
        params = GetScriptRequest.model_validate(data)
        response = self.request(self._get_script_endpoint(params.script_id).with_params(params))
        return response

    @track_usage("cloud.script.delete")
    def delete(self, **data: Unpack[DeleteScriptRequestDict]) -> None:
        """
        Delete a script.

        Args:
            script_id: The ID of the script to delete.
            **data: Unpacked dictionary containing parameters for the request.
        """
        request = DeleteScriptRequest.model_validate(data)
        _ = self.request(self._delete_script_endpoint(request.script_id).with_params(request))

    @track_usage("cloud.script.list")
    def list(self, **data: Unpack[ListScriptsRequestDict]) -> ListScriptsResponse:
        """
        List all available scripts.

        Args:
            **data: Unpacked dictionary containing parameters for the request.

        Returns:
            ListScriptsResponse: Response containing the list of scripts.
        """
        params = ListScriptsRequest.model_validate(data)
        response = self.request(self._list_scripts_endpoint().with_params(params))
        return response


class RemoteScript:
    def __init__(self, client: ScriptsClient, response: GetScriptResponse):
        self.client: ScriptsClient = client
        self.response: GetScriptResponse | GetScriptWithLinkResponse = response

    def run(self) -> BaseModel:
        raise NotImplementedError("Not implemented")

    def update(self, script_path: str, version: str | None = None) -> None:
        self.response = self.client.update(script_id=self.response.script_id, script_path=script_path, version=version)
        logger.info(
            f"[Script] {self.response.script_id} updated successfully to version {self.response.latest_version}."
        )

    def delete(self) -> None:
        _ = self.client.delete(script_id=self.response.script_id)
        logger.info(f"[Script] {self.response.script_id} deleted successfully.")

    def get_url(self, version: str | None = None) -> str:
        if not isinstance(self.response, GetScriptWithLinkResponse) or version != self.response.latest_version:
            self.response = self.client.get(script_id=self.response.script_id, version=version)
        return self.response.url

    def download(self, script_path: str, version: str | None = None) -> str:
        if not script_path.endswith(".py"):
            raise ValueError(f"Script path must end with .py, got '{script_path}'")

        url = self.get_url(version=version)
        response = requests.get(url)
        if response.status_code != 200:
            raise ValueError(f"Failed to download script from {url}")

        with open(script_path, "w") as f:
            _ = f.write(response.text)
        logger.info(f"[Script] {self.response.script_id} downloaded successfully to {script_path}.")
        return response.text


@final
class RemoteScriptFactory:
    def __init__(self, client: ScriptsClient):
        self.client = client

    @overload
    def __call__(self, /, script_id: str) -> RemoteScript: ...

    @overload
    def __call__(self, **data: Unpack[CreateScriptRequestDict]) -> RemoteScript: ...

    def __call__(self, script_id: str | None = None, **data: Unpack[CreateScriptRequestDict]) -> RemoteScript:  # pyright: ignore[reportInconsistentOverload]
        if script_id is None:
            response = self.client.create(**data)
            logger.info(f"[Script] {response.script_id} created successfully.")
        else:
            response = self.client.get(script_id=script_id)
            logger.info(f"[Script] {response.script_id} retrieved successfully.")
        return RemoteScript(self.client, response)
