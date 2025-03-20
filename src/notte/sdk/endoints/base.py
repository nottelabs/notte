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
        return self.model_copy(update={"request": request})

    def with_params(self, params: BaseModel) -> Self:
        # return deep copy of self with the params set
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
        self.server_url = self.LOCAL_SERVER_URL
        return self

    def remote(self) -> Self:
        self.server_url = self.DEFAULT_SERVER_URL
        return self

    @staticmethod
    @abstractmethod
    def endpoints() -> Sequence[NotteEndpoint[BaseModel]]:
        pass

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def request_path(self, endpoint: NotteEndpoint[TResponse]) -> str:
        if self.base_endpoint_path is None:
            return f"{self.server_url}/{endpoint.path}"
        return f"{self.server_url}/{self.base_endpoint_path}/{endpoint.path}"

    def _request(self, endpoint: NotteEndpoint[TResponse]) -> requests.Response:
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
        response: Any = self._request(endpoint)
        if not isinstance(response, dict):
            raise NotteAPIError(path=endpoint.path, response=response)
        return endpoint.response.model_validate(response)

    def request_list(self, endpoint: NotteEndpoint[TResponse]) -> Sequence[TResponse]:
        # Handle the case where TResponse is a list of BaseModel
        response_list: Any = self._request(endpoint)
        if not isinstance(response_list, list):
            raise NotteAPIError(path=endpoint.path, response=response_list)
        return [endpoint.response.model_validate(item) for item in response_list]  # pyright: ignore[reportUnknownVariableType]
