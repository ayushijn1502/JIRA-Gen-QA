"""
Domain models -- the "data shapes" that flow through the entire system.

These are plain data containers (Pydantic models) with no business logic
and no dependency on any framework.  Every layer -- CLI, agents,
infrastructure -- speaks the same language because they all use these models.

Think of them as the "forms" that get passed between departments in an office:
everyone fills in the same fields, so nobody misunderstands the data.
"""

from __future__ import annotations

from typing import TypedDict

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Pydantic models (validated, serialisable)
# ---------------------------------------------------------------------------


class JiraTicket(BaseModel):
    """
    Represents one JIRA ticket after we've pulled out the important bits.
    The agent reads this to understand *what* needs testing.
    """

    id: str = Field(description="JIRA ticket key, e.g. PROJ-123")
    title: str = Field(description="Short summary / title of the ticket")
    description: str = Field(description="Full description or user story")
    acceptance_criteria: list[str] = Field(
        default_factory=list,
        description="List of acceptance-criteria bullet points",
    )


class TestPlan(BaseModel):
    """
    The output of the *Analyze* step -- a blueprint that tells the Coder
    agent exactly what tests to write, where to put them, and what
    existing code to reference.
    """

    ticket_id: str = Field(description="The JIRA ticket this plan is for")
    target_file: str = Field(
        description="Path (relative to target_framework/) where the new test file should go"
    )
    test_scenarios: list[str] = Field(
        description="One-line description of each test case to generate"
    )
    relevant_context: list[str] = Field(
        default_factory=list,
        description="Code snippets retrieved from RAG that the Coder should reference",
    )


class GeneratedTest(BaseModel):
    """
    The output of the *Generate* step -- the actual pytest code that the
    Coder agent produced, plus a short explanation of what it does.
    """

    file_path: str = Field(description="Where to write this file on disk")
    code: str = Field(description="The full Python source code of the test file")
    explanation: str = Field(
        description="Plain-English summary of what the generated tests cover"
    )


class TestMatrixRow(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    testcase: str = Field(description="Test case identifier/title")
    description: str = Field(
        description="Short description of the case",
        validation_alias=AliasChoices("description", "Description"),
    )
    pre_condition: str = Field(
        description="Required preconditions",
        validation_alias=AliasChoices("pre_condition", "PreCondition", "precondition"),
    )
    test_steps: str = Field(
        description="Execution steps",
        validation_alias=AliasChoices("test_steps", "TestSteps"),
    )
    expected_results: str = Field(
        description="Expected result",
        validation_alias=AliasChoices(
            "expected_results", "Expected Results", "Expected_Results", "ExpectedResults"
        ),
    )


class TestMatrixDocument(BaseModel):
    rows: list[TestMatrixRow] = Field(default_factory=list)


class VerificationResult(BaseModel):
    """
    The output of the *Verify* step -- did pytest pass or fail,
    and what did it print?
    """

    passed: bool = Field(description="True if every test passed")
    output: str = Field(default="", description="Stdout from pytest")
    error_log: str = Field(default="", description="Stderr / traceback from pytest")


# ---------------------------------------------------------------------------
# LangGraph state (must be a TypedDict, not a Pydantic model)
# ---------------------------------------------------------------------------


class GraphState(TypedDict, total=False):
    """
    The "shared whiteboard" that every node in the LangGraph state machine
    can read from and write to.  Each node updates only the keys it owns.

    `total=False` means every key is optional -- nodes only supply the
    fields they've computed so far.
    """

    ticket: JiraTicket
    plan: TestPlan
    generated_test: GeneratedTest
    verification: VerificationResult
    retry_count: int
    max_retries: int
    error_history: list[str]
    phase: str
    test_matrix_csv_path: str
