import pytest
import requests_mock as rm

from target_framework.src.course_module import CourseModule, CourseStatus
from target_framework.src.base_api_client import BaseApiClient


class TestCourseModule:
    """Tests for CourseModule functionality."""

    def test_add_quiz_available_for_approved_derivative_course(self, base_url: str, api_client: BaseApiClient) -> None:
        """Verify 'Add Quiz' option is available for Approved Derivative Courses."""
        course_id = 1
        course_data = {
            "id": course_id,
            "title": "Derivative Course",
            "status": CourseStatus.APPROVED,
            "is_derivative": True,
            "options": ["Audio", "Video"]
        }

        course_module = CourseModule(api_client=api_client)

        with rm.Mocker() as m:
            m.get(f"{base_url}/courses/{course_id}", json=course_data)
            course = course_module.get_course(course_id)

        assert "Add Quiz" in course.options

    def test_add_quiz_disabled_for_non_approved_derivative_course(self, base_url: str, api_client: BaseApiClient) -> None:
        """Verify 'Add Quiz' option is disabled for non-Approved Derivative Courses."""
        course_id = 2
        course_data = {
            "id": course_id,
            "title": "Pending Derivative Course",
            "status": CourseStatus.PENDING,
            "is_derivative": True,
            "options": ["Audio", "Video"]
        }
        error_message = "Cannot add quiz to a course that is not approved."

        course_module = CourseModule(api_client=api_client)

        with rm.Mocker() as m:
            m.get(f"{base_url}/courses/{course_id}", json=course_data)
            course = course_module.get_course(course_id)
            m.post(f"{base_url}/courses/{course_id}/quizzes", status_code=400, json={"detail": error_message})

        assert "Add Quiz" not in course.options
        with pytest.raises(Exception, match=error_message):
            course_module.add_quiz(course_id)
