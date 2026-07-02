# Test matrix (CSV) step

You are documenting **manual-style test cases** before any code is generated. Output must be **complete and review-ready**: every CSV cell must contain meaningful text (use `N/A` only where a field truly does not apply — never leave a field empty).

## Row count

- Produce **exactly one row per test scenario** from the test plan. If the plan lists **N** scenarios, output **N** rows (same N; do not invent extra cases).
- If the plan has **no** scenarios, derive **at most two** rows from the JIRA ticket (one positive path, one negative or edge path).

## Column rules (all required in every row)

### testcase (short title / ID)

- **Must not be empty.** Must not repeat the full description as the testcase string.
- Use a **unique, human-readable title** per row, ideally tied to the ticket, for example: `{TICKET_KEY} — Happy path: …` or `{TICKET_KEY} — Negative: …` (replace `{TICKET_KEY}` with the actual key from the prompt, e.g. `PROJ-123`).
- Maximum **120 characters**. No generic placeholders like `test1`, `case1`, or `scenario` unless the scenario text itself is the only identifier (still prefer `TICKET — short label`).

### description

- **1–2 sentences** stating **what** behaviour is under test and **why** it matters for this ticket or acceptance criteria.
- Must not be empty.

### precondition

- Describe **concrete** setup: environment, data, user role, feature flag, URL, logged-in state, or dependencies.
- Use **`N/A`** only when there is genuinely no precondition beyond “system is up” — in that case you may write `N/A` or one explicit line such as `Clean install; default configuration.`

### test_steps

- **Numbered steps**, newline-separated (`1. …`, `2. …`, …).
- Each step must be **actionable** by a human QA engineer (clear action, object, and where to act).
- Must not be empty.

### expected_results

- **Observable** outcomes after the steps (what the user sees, API response, DB state, error message, etc.).
- Tie expectations to **acceptance criteria** where possible.
- Must not be empty.

## Output format

Return **only** structured data matching the schema: a JSON object with a `rows` array; each element has exactly these keys: `testcase`, `description`, `precondition`, `test_steps`, `expected_results`.

- **No** markdown code fences, **no** commentary before or after the JSON.
- **No** null values; use strings only. Do not omit keys.

## Quality bar

A reviewer should be able to execute the matrix **without opening the JIRA ticket**, using only your rows plus the ticket context already in the prompt. Vague steps like “verify behaviour” or “test as per ticket” are **not** acceptable — be specific.

