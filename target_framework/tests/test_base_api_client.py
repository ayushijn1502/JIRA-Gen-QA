"""
Tests for BaseApiClient -- the shared HTTP wrapper.
We mock the actual HTTP calls with `requests_mock` so no network traffic happens.
"""

from __future__ import annotations

import pytest
import requests_mock as rm

from target_framework.src.base_api_client import ApiError, BaseApiClient


class TestBaseApiClientGet:
    """Tests for the GET method."""

    def test_get_returns_json(self, api_client: BaseApiClient, base_url: str) -> None:
        """A successful GET should return the parsed JSON body."""
        with rm.Mocker() as m:
            m.get(f"{base_url}/items", json={"items": [1, 2, 3]})
            result = api_client.get("/items")
        assert result == {"items": [1, 2, 3]}

    def test_get_with_query_params(self, api_client: BaseApiClient, base_url: str) -> None:
        """Query params should be forwarded to the request."""
        with rm.Mocker() as m:
            m.get(f"{base_url}/items", json={"page": 2})
            result = api_client.get("/items", params={"page": 2})
        assert result == {"page": 2}

    def test_get_raises_api_error_on_404(self, api_client: BaseApiClient, base_url: str) -> None:
        """A 404 response must raise ApiError with the right status code."""
        with rm.Mocker() as m:
            m.get(f"{base_url}/missing", status_code=404, text="Not Found")
            with pytest.raises(ApiError) as exc_info:
                api_client.get("/missing")
        assert exc_info.value.status_code == 404


class TestBaseApiClientPost:
    """Tests for the POST method."""

    def test_post_sends_json_and_returns_response(
        self, api_client: BaseApiClient, base_url: str
    ) -> None:
        """POST should send a JSON body and return the parsed response."""
        with rm.Mocker() as m:
            m.post(f"{base_url}/items", json={"id": 99, "name": "new"}, status_code=201)
            result = api_client.post("/items", data={"name": "new"})
        assert result == {"id": 99, "name": "new"}

    def test_post_raises_api_error_on_500(
        self, api_client: BaseApiClient, base_url: str
    ) -> None:
        """A 500 response must raise ApiError."""
        with rm.Mocker() as m:
            m.post(f"{base_url}/items", status_code=500, text="Internal Server Error")
            with pytest.raises(ApiError) as exc_info:
                api_client.post("/items", data={})
        assert exc_info.value.status_code == 500
