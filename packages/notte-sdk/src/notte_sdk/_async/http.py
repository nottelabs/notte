"""Async HTTP client for the Notte SDK."""

from __future__ import annotations

from typing import Any

import httpx
from notte_core import __version__ as notte_core_version


class AsyncHTTPClient:
    """Async HTTP client using httpx.AsyncClient."""

    DEFAULT_TIMEOUT_SECONDS: float = 60.0

    def __init__(
        self,
        token: str,
        base_url: str,
        timeout: float | None = None,
    ):
        """Initialize the async HTTP client.

        Args:
            token: API token for authentication.
            base_url: Base URL for all requests.
            timeout: Request timeout in seconds.
        """
        self._token: str = token
        self._base_url: str = base_url.rstrip("/")
        self._timeout: float = timeout or self.DEFAULT_TIMEOUT_SECONDS
        self._client: httpx.AsyncClient | None = None

    def _get_default_headers(self) -> dict[str, str]:
        """Get default headers for all requests."""
        return {
            "Authorization": f"Bearer {self._token}",
            "x-notte-sdk-version": notte_core_version,
            "x-notte-request-origin": "sdk",
        }

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure the client is initialized."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=self._get_default_headers(),
                timeout=self._timeout,
            )
        return self._client

    async def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        data: Any | None = None,
        files: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        """Make an async HTTP request.

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE).
            path: Request path (will be appended to base_url).
            headers: Additional headers to send.
            params: Query parameters.
            json: JSON body to send.
            data: Form data to send.
            files: Files to upload.
            timeout: Request-specific timeout override.

        Returns:
            The httpx Response object.
        """
        client = await self._ensure_client()

        # Merge headers
        request_headers = dict(self._get_default_headers())
        if headers:
            request_headers.update(headers)

        return await client.request(
            method=method,
            url=path,
            headers=request_headers,
            params=params,
            json=json,
            data=data,
            files=files,
            timeout=timeout or self._timeout,
        )

    async def get(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        """Make a GET request."""
        return await self.request(
            "GET",
            path,
            headers=headers,
            params=params,
            timeout=timeout,
        )

    async def post(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        data: Any | None = None,
        files: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        """Make a POST request."""
        return await self.request(
            "POST",
            path,
            headers=headers,
            params=params,
            json=json,
            data=data,
            files=files,
            timeout=timeout,
        )

    async def patch(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        data: Any | None = None,
        files: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        """Make a PATCH request."""
        return await self.request(
            "PATCH",
            path,
            headers=headers,
            params=params,
            json=json,
            data=data,
            files=files,
            timeout=timeout,
        )

    async def delete(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        """Make a DELETE request."""
        return await self.request(
            "DELETE",
            path,
            headers=headers,
            params=params,
            timeout=timeout,
        )

    async def stream(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        """Make a streaming request.

        Returns a Response object that can be used as an async context manager
        for streaming the response body.
        """
        client = await self._ensure_client()

        request_headers = dict(self._get_default_headers())
        if headers:
            request_headers.update(headers)

        # For streaming, we need to use the stream context manager
        return await client.stream(
            method=method,
            url=path,
            headers=request_headers,
            params=params,
            json=json,
            timeout=timeout or self._timeout,
        ).__aenter__()

    async def aclose(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
