from __future__ import annotations

import pytest
import requests_mock as rm

from target_framework.src.user_service import UserService


class TestMockApiUsers:
    """Tests for the mock API endpoints related to users."""

    def test_get_user_valid_id_returns_200_and_schema(
        self,
        user_service: UserService,
        base_url: str,
        sample_user: dict,
    ) -> None:
        """GET /api/v1/mock/users/{userId} with a valid userId returns 200 OK and correct schema."""
        user_id = 1
        with rm.Mocker() as m:
            m.get(f"{base_url}/api/v1/mock/users/{user_id}", json=sample_user, status_code=200)
            result = user_service.get_mock_user(user_id)
        assert result == sample_user

    def test_get_user_invalid_id_format_returns_400(
        self,
        user_service: UserService,
        base_url: str,
    ) -> None:
        """GET /api/v1/mock/users/{userId} with an invalid userId format returns 400 Bad Request."""
        invalid_user_id = "abc"
        with rm.Mocker() as m:
            m.get(f"{base_url}/api/v1/mock/users/{invalid_user_id}", status_code=400, text="Bad Request")
            with pytest.raises(ValueError) as exc_info:
                user_service.get_mock_user(invalid_user_id)
        assert "Invalid user ID format" in str(exc_info.value)
