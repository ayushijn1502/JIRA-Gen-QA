"""
Shared test fixtures for all target_framework tests.
Fixtures are like "pre-made ingredients" -- pytest automatically
injects them into any test function that asks for them by name.
"""

from __future__ import annotations

import pytest

from target_framework.src.base_api_client import BaseApiClient
from target_framework.src.user_service import UserService


@pytest.fixture()
def base_url() -> str:
    """The fake API base URL used across all tests."""
    return "https://api.example.com"


@pytest.fixture()
def api_client(base_url: str) -> BaseApiClient:
    """A real BaseApiClient pointing at our fake URL (mocked at the HTTP level)."""
    return BaseApiClient(base_url=base_url)


@pytest.fixture()
def user_service(api_client: BaseApiClient) -> UserService:
    """A UserService wired to the test api_client."""
    return UserService(api_client=api_client)


@pytest.fixture()
def sample_user() -> dict:
    """A reusable user payload returned by mock API responses."""
    return {"id": 1, "name": "Alice", "email": "alice@example.com"}


@pytest.fixture()
def sample_users(sample_user: dict) -> list[dict]:
    """A list of users for list-endpoint mocks."""
    return [
        sample_user,
        {"id": 2, "name": "Bob", "email": "bob@example.com"},
    ]
