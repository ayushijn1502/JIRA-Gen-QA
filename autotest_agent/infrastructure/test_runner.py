"""
Test Runner -- executes pytest on a given file and reports pass/fail.

This is the "quality checker" in the pipeline: after the Coder agent
writes a test file, we run it through pytest to see if it actually works.
If it fails, the error output gets fed back to the Coder for a retry.

Usage:
    runner = PytestRunner()
    result = runner.run_tests("target_framework/tests/test_new.py")
    if not result.passed:
        print(result.error_log)
"""

from __future__ import annotations

import subprocess

from autotest_agent.domain.models import VerificationResult
from autotest_agent.domain.ports import TestRunnerPort


class PytestRunner(TestRunnerPort):
    """
    Concrete implementation of TestRunnerPort.
    Shells out to `pytest` as a subprocess and captures the output.
    """

    def run_tests(self, test_file_path: str) -> VerificationResult:
        """
        Run pytest against one test file.
        Returns a VerificationResult telling you whether it passed
        and what pytest printed.
        """
        result = subprocess.run(
            ["python", "-m", "pytest", test_file_path, "-v", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        return VerificationResult(
            passed=result.returncode == 0,
            output=result.stdout,
            error_log=result.stderr if result.returncode != 0 else "",
        )
