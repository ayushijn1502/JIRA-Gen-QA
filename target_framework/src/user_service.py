"""
Business-logic layer for user operations.  It does NOT know how HTTP works --
it just calls `BaseApiClient` methods and transforms the data.

Think of it as the "manager" that decides *what* to ask the API,
while the ApiClient decides *how* to ask it.

Usage:
    svc = UserService(api_client=my_client)
    user = svc.get_user(42)
    created = svc.create_user("Alice", "alice@example.com")
"""

from __future__ import annotations

from target_framework.src.base_api_client import BaseApiClient


class UserNotFoundError(Exception):
    """Raised when a requested user does not exist."""


class UserService:
    """
    High-level operations on the /users resource.
    Every method returns plain dicts so callers don't need to know
    about the HTTP layer at all.
    """

    def __init__(self, api_client: BaseApiClient) -> None:
        self._client = api_client

    def get_user(self, user_id: int) -> dict:
        """
        Fetch a single user by ID.
        Raises UserNotFoundError if the API returns a 404.
        """
        from target_framework.src.base_api_client import ApiError

        try:
            return self._client.get(f"/users/{user_id}")
        except ApiError as exc:
            if exc.status_code == 404:
                raise UserNotFoundError(f"User {user_id} not found") from exc
            raise

    def list_users(self) -> list[dict]:
        """Return every user the API knows about."""
        return self._client.get("/users")

    def create_user(self, name: str, email: str) -> dict:
        """
        Create a new user and return the API response
        (usually the created user object with an assigned ID).
        """
        return self._client.post("/users", data={"name": name, "email": email})
