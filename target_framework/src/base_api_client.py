"""
A simple HTTP client wrapper that every service in the project uses
to talk to external APIs. Think of it as a shared "remote control" --
instead of each service writing its own HTTP logic, they all go through
this one class.

Usage:
    client = BaseApiClient(base_url="https://api.example.com")
    users = client.get("/users")
    new_user = client.post("/users", data={"name": "Alice"})
"""

from __future__ import annotations

from typing import Any

import requests


class ApiError(Exception):
    """Raised when an API call returns a non-success status code."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"API Error {status_code}: {message}")


class BaseApiClient:
    """
    Thin wrapper around the `requests` library.
    Every service (UserService, OrderService, etc.) gets one of these
    injected so we can swap it out with a mock during tests.
    """

    def __init__(self, base_url: str, timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Send a GET request and return the JSON response as a dict.
        Raises ApiError if the server returns a 4xx/5xx status.
        """
        response = self._session.get(
            f"{self.base_url}{path}",
            params=params,
            timeout=self.timeout,
        )
        return self._handle_response(response)

    def post(self, path: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Send a POST request with a JSON body and return the JSON response.
        Raises ApiError if the server returns a 4xx/5xx status.
        """
        response = self._session.post(
            f"{self.base_url}{path}",
            json=data,
            timeout=self.timeout,
        )
        return self._handle_response(response)

    def _handle_response(self, response: requests.Response) -> dict[str, Any]:
        """Check status code and parse JSON, or raise ApiError."""
        if not response.ok:
            raise ApiError(response.status_code, response.text)
        return response.json()
