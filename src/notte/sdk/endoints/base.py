import os
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any, ClassVar, Generic, Literal, Self, TypeVar

import requests
from loguru import logger
from pydantic import BaseModel

from notte.errors.sdk import AuthenticationError, NotteAPIError

TResponse = TypeVar("TResponse", bound=BaseModel, covariant=True)


class NotteEndpoint(BaseModel, Generic[TResponse]):
    path: str
    response: type[TResponse]
    request: BaseModel | None = None
    method: Literal["GET", "POST", "DELETE"]
    params: BaseModel | None = None

    def with_request(self, request: BaseModel) -> Self:
        # return deep copy of self with the request set
        """
        Return a deep copy of the endpoint with the given request model.
        
        Creates a new instance of the endpoint by updating the request field with the
        provided BaseModel. This allows for chaining modifications without mutating
        the original instance.
        
        Args:
            request: A BaseModel instance representing the new request data.
        
        Returns:
            A new instance of the endpoint with the updated request field.
        """
        return self.model_copy(update={"request": request})

    def with_params(self, params: BaseModel) -> Self:
        # return deep copy of self with the params set
        """
        Return a deep copy of the endpoint with updated request parameters.
        
        Creates a new instance with its 'params' attribute set to the specified Pydantic model,
        allowing for immutable configuration updates without altering the original endpoint.
        
        Args:
            params: A Pydantic model instance containing the new request parameters.
        
        Returns:
            A new endpoint instance with the updated parameters.
        """
        return self.model_copy(update={"params": params})


class BaseClient(ABC):
    DEFAULT_SERVER_URL: ClassVar[str] = "https://api.notte.cc"
    LOCAL_SERVER_URL: ClassVar[str] = "http://localhost:8000"

    def __init__(
        self,
        base_endpoint_path: str | None,
        api_key: str | None = None,
        server_url: str | None = None,
    ):
        """
        Initialize the API client with configuration settings.
        
        This constructor retrieves the API key from the provided parameter or the "NOTTE_API_KEY" 
        environment variable, raising an AuthenticationError if no API key is found. It also sets 
        the server URL to the given value or defaults to DEFAULT_SERVER_URL and initializes the 
        endpoints mapping from the available endpoints.
        
        Args:
            base_endpoint_path: Base path to prepend to endpoint paths.
            api_key: API key for authentication; if absent, it is retrieved from the environment.
            server_url: URL for the API server; defaults to DEFAULT_SERVER_URL if not provided.
        
        Raises:
            AuthenticationError: If an API key is neither provided nor available in the environment.
        """
        token = api_key or os.getenv("NOTTE_API_KEY")
        if token is None:
            raise AuthenticationError("NOTTE_API_KEY needs to be provided")
        self.token: str = token
        self.server_url: str = server_url or self.DEFAULT_SERVER_URL
        self._endpoints: dict[str, NotteEndpoint[BaseModel]] = {
            endpoint.path: endpoint for endpoint in self.endpoints()
        }
        self.base_endpoint_path: str | None = base_endpoint_path

    def local(self) -> Self:
        """
        Sets the client to use the local server.
        
        Updates the client's server URL to the local server address and returns the updated client instance.
        """
        self.server_url = self.LOCAL_SERVER_URL
        return self

    def remote(self) -> Self:
        """
        Set the client to use the default remote server.
        
        Updates the client's server URL to the default remote endpoint and returns the
        client instance to allow method chaining.
        """
        self.server_url = self.DEFAULT_SERVER_URL
        return self

    @staticmethod
    @abstractmethod
    def endpoints() -> Sequence[NotteEndpoint[BaseModel]]:
        """
        Returns a sequence of available API endpoints.
        
        Subclasses must override this method to provide the list of NotteEndpoint
        instances that define the API endpoints, including their paths, HTTP methods,
        and expected response models.
        """
        pass

    def headers(self) -> dict[str, str]:
        """
        Generates the authorization header for API requests.
        
        Returns:
            dict[str, str]: A dictionary containing the "Authorization" header with the bearer token.
        """
        return {"Authorization": f"Bearer {self.token}"}

    def request_path(self, endpoint: NotteEndpoint[TResponse]) -> str:
        """
        Constructs the full URL for the given API endpoint.
        
        This method combines the server URL, an optional base endpoint path, and the endpoint's path to form
        the complete URL for an API request. If no base endpoint path is set, the URL is built using only the
        server URL and the endpoint's path.
        
        Args:
            endpoint: The API endpoint containing the path segment to append.
        
        Returns:
            The full request URL as a string.
        """
        if self.base_endpoint_path is None:
            return f"{self.server_url}/{endpoint.path}"
        return f"{self.server_url}/{self.base_endpoint_path}/{endpoint.path}"

    def _request(self, endpoint: NotteEndpoint[TResponse]) -> requests.Response:
        """
        Executes an HTTP request for the specified endpoint and returns its JSON response.
        
        This method constructs the full URL and request headers from the endpoint details, then dispatches the HTTP request based on the method specified (GET, POST, or DELETE). A POST request must include a request model; otherwise, a ValueError is raised. If the response status is not 200 or includes an error detail, a NotteAPIError is raised.
        
        Args:
            endpoint: A NotteEndpoint instance containing the endpoint path, HTTP method, and
                any associated request or parameter data.
        
        Returns:
            The parsed JSON response from the API.
        
        Raises:
            ValueError: If a POST request is made without a specified request model.
            NotteAPIError: If the response indicates an error via its status code or detail.
        """
        headers = self.headers()
        url = self.request_path(endpoint)
        params = endpoint.params.model_dump() if endpoint.params is not None else None
        logger.info(
            f"Making `{endpoint.method}` request to `{endpoint.path} (i.e `{url}`) with params `{params}` and request `{endpoint.request}`"
        )
        match endpoint.method:
            case "GET":
                response = requests.get(url=url, headers=headers, params=params)
            case "POST":
                if endpoint.request is None:
                    raise ValueError("Request model is required for POST requests")
                response = requests.post(
                    url=url,
                    headers=headers,
                    json=endpoint.request.model_dump(),
                    params=params,
                )
            case "DELETE":
                response = requests.delete(
                    url=url,
                    headers=headers,
                    params=params,
                )
        response_dict: Any = response.json()
        if response.status_code != 200 or "detail" in response_dict:
            raise NotteAPIError(path=endpoint.path, response=response)
        return response_dict

    def request(self, endpoint: NotteEndpoint[TResponse]) -> TResponse:
        """
        Send a request to the specified API endpoint and return the validated response.
        
        This method delegates the HTTP call to an internal function and ensures that the
        response is a JSON object. If the response is not a dictionary, it raises a
        NotteAPIError with details of the endpoint path and received response. Otherwise,
        the response is validated using the endpoint's expected response model and returned.
        
        Args:
            endpoint: A NotteEndpoint instance containing API endpoint details and the expected response model.
        
        Returns:
            The response validated against the endpoint's response model.
        
        Raises:
            NotteAPIError: If the received response is not a valid JSON object.
        """
        response: Any = self._request(endpoint)
        if not isinstance(response, dict):
            raise NotteAPIError(path=endpoint.path, response=response)
        return endpoint.response.model_validate(response)

    def request_list(self, endpoint: NotteEndpoint[TResponse]) -> Sequence[TResponse]:
        # Handle the case where TResponse is a list of BaseModel
        """
        Processes an API request expecting a list of responses.
        
        Sends a request using the specified endpoint and validates that the response
        is a list. Each element in the returned list is validated using the endpoint's
        defined response model. Raises a NotteAPIError if the response data is not a list.
        
        Args:
            endpoint: The API endpoint definition including the request details and the expected response model.
        
        Returns:
            A sequence of validated response model instances.
        """
        response_list: Any = self._request(endpoint)
        if not isinstance(response_list, list):
            raise NotteAPIError(path=endpoint.path, response=response_list)
        return [endpoint.response.model_validate(item) for item in response_list]  # pyright: ignore[reportUnknownVariableType]
