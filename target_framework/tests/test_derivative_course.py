import pytest
from unittest.mock import MagicMock

from target_framework.src.course_module import CourseModule
from target_framework.src.course_module import CourseStatus


class TestDerivativeCourse:
    """Tests for Derivative Course functionality."""

    def test_create_derivative_course_success(self, base_url: str, api_client: MagicMock) -> None:
        """Successfully create a derivative course with all required fields filled."""
        course_id = 1
        course_data = {
            "id": course_id,
            "title": "My Derivative Course",
            "status": CourseStatus.PENDING,
            "is_derivative": True,
            "options": ["Audio", "Video"]
        }
        expected_course = {
            "id": course_id,
            "title": "My Derivative Course",
            "status": CourseStatus.PENDING,
            "is_derivative": True,
            "options": ["Audio", "Video"]
        }

        course_module = CourseModule(api_client=api_client)

        with pytest.mock.patch('requests_mock.Mocker') as m:
            m.post(f"{base_url}/courses", json=expected_course, status_code=201)
            created_course = course_module.create_derivative_course(
                title="My Derivative Course",
                options=["Audio", "Video"]
            )

        assert created_course == expected_course

    def test_create_derivative_course_missing_fields(self, base_url: str, api_client: MagicMock) -> None:
        """Attempt to create a derivative course without filling all required fields."""
        course_module = CourseModule(api_client=api_client)

        # Mocking the API call to return an error for incomplete data
        with pytest.mock.patch('requests_mock.Mocker') as m:
            m.post(f"{base_url}/courses", json={"detail": "Missing required fields"}, status_code=400)

            # Expecting an exception when required fields are missing
            with pytest.raises(Exception, match="Missing required fields"):
                course_module.create_derivative_course(title="Incomplete Course")
