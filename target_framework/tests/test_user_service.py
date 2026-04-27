"""
Tests for UserService -- the business-logic layer.
We mock HTTP responses so UserService thinks it's talking to a real API.
"""

from __future__ import annotations

import pytest
import requests_mock as rm

from target_framework.src.user_service import UserNotFoundError, UserService


class TestGetUser:
    """Tests for fetching a single user."""

    def test_returns_user_dict(
        self, user_service: UserService, base_url: str, sample_user: dict
    ) -> None:
        with rm.Mocker() as m:
            m.get(f"{base_url}/users/1", json=sample_user)
            result = user_service.get_user(1)
        assert result == sample_user

    def test_raises_not_found_for_missing_user(
        self, user_service: UserService, base_url: str
    ) -> None:
        with rm.Mocker() as m:
            m.get(f"{base_url}/users/999", status_code=404, text="Not Found")
            with pytest.raises(UserNotFoundError):
                user_service.get_user(999)


class TestListUsers:
    """Tests for listing all users."""

    def test_returns_list_of_users(
        self, user_service: UserService, base_url: str, sample_users: list[dict]
    ) -> None:
        with rm.Mocker() as m:
            m.get(f"{base_url}/users", json=sample_users)
            result = user_service.list_users()
        assert result == sample_users


class TestCreateUser:
    """Tests for creating a new user."""

    def test_returns_created_user(self, user_service: UserService, base_url: str) -> None:
        created = {"id": 3, "name": "Charlie", "email": "charlie@example.com"}
        with rm.Mocker() as m:
            m.post(f"{base_url}/users", json=created, status_code=201)
            result = user_service.create_user("Charlie", "charlie@example.com")
        assert result == created
