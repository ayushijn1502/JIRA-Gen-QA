# Knowledge Base -- Testing Framework Rules

These are the coding standards that every generated test must follow.
The AI agents read this file before writing any code, so it acts as
a "style guide" enforced at generation time.

---

## File & Naming Conventions

- **Only** write new test files under `target_framework/tests/` (never under `src/`, repo root, or other trees).
- Test files live in `target_framework/tests/`.
- File names: `test_<module_name>.py`.
- Test classes: `Test<Feature>` (PascalCase, no underscores).
- Test functions: `test_<action>_<expected_outcome>` (snake_case).

## Fixture Rules

- Always prefer fixtures over inline setup code.
- Shared fixtures go in `tests/conftest.py`.
- Use the narrowest fixture scope that works (`function` by default).
- Never create a fixture that duplicates an existing one -- check conftest first.

## Mocking Rules

- Mock ALL external calls: HTTP requests, database queries, file I/O.
- Use `requests_mock` for HTTP mocking (already in the project dependencies).
- Use `pytest.MonkeyPatch` or `unittest.mock.patch` for other externals.
- Never let a test hit a real network endpoint.

## Assertion Rules

- Every test must have at least one `assert` statement.
- Prefer specific assertions (`assert result == expected`) over truthy checks.
- Use `pytest.raises` for expected exceptions -- always check the exception type.

## Structure Rules

- One test function per scenario. No combined "test_everything" functions.
- Group related tests in a class (e.g. `TestGetUser`, `TestCreateUser`).
- Keep test bodies short: arrange, act, assert. No more than 15 lines.

## Docstrings

- Every test function should have a one-line docstring explaining
what behavior it verifies.

## Imports

- Import from `target_framework.src.<module>`, not relative imports.
- Keep imports sorted: stdlib, third-party, local.

