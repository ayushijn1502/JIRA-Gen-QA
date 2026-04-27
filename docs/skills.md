# Skills & Tools

This file describes the tools (skills) available to the agents.
Each tool is a specific capability the system can use during execution.

---

## jira_query

**Purpose:** Fetch a JIRA ticket by its ID and return structured data.

**Input:** Ticket ID (e.g. `PROJ-123`).

**Output:** A dict with `id`, `title`, `description`, and
`acceptance_criteria` (list of strings).

**When to use:** At the start of every run, in the Analyze phase.

---

## rag_search

**Purpose:** Search the indexed codebase for code snippets relevant
to a natural-language question.

**Input:** A question string and an optional `top_k` count.

**Output:** A list of code chunks (strings) ranked by relevance.

**When to use:** During analysis, to find existing tests, fixtures,
and source code that relate to the new test scenarios.

---

## file_write

**Purpose:** Write generated test code to a file on disk.

**Input:** File path (relative to target_framework/) and file content.

**Output:** Confirmation that the file was written.

**When to use:** After the Coder agent produces test code, before
running verification.

---

## pytest_run

**Purpose:** Execute pytest on a specific test file and capture results.

**Input:** Path to the test file.

**Output:** Pass/fail status, stdout, and stderr.

**When to use:** In the Verify phase, to check if generated tests pass.

---

## git_push

**Purpose:** Create a branch, commit files, and open a GitHub PR.

**Input:** Branch name, file paths, commit message, PR title, and PR body.

**Output:** The URL of the created pull request.

**When to use:** In the Deploy phase, after the user approves the code.
