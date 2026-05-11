"""
Where generated pytest files are allowed to live.

The POC always writes new tests under ``target_framework/tests/`` so runs
never scatter files elsewhere by accident (even if the LLM suggests another path).
"""

from __future__ import annotations

import re
from pathlib import Path


def resolve_generated_test_path(
    suggested_file_path: str,
    ticket_id: str,
    target_framework_path: str,
) -> str:
    """
    Pick the final path for a generated test file.

    Rules (simple):
    - Directory is always ``<target_framework>/tests/`` (folder is created if needed).
    - File name comes from the LLM suggestion only if it looks like a safe ``test_*.py``;
      otherwise we use ``test_autotest_<ticket>.py``.
    - Return path relative to the **repository root** (parent of ``target_framework``),
      using forward slashes, e.g. ``target_framework/tests/test_autotest_kan_1.py``.
      If that relative path cannot be computed, return an absolute path string instead.
    """
    fw = Path(target_framework_path).expanduser().resolve()
    tests_dir = (fw / "tests").resolve()
    tests_dir.mkdir(parents=True, exist_ok=True)
    repo_root = fw.parent.resolve()

    safe_ticket = re.sub(r"[^a-zA-Z0-9]+", "_", ticket_id).strip("_").lower() or "ticket"
    default_name = f"test_autotest_{safe_ticket}.py"

    raw = (suggested_file_path or "").strip().replace("\\", "/")
    if ".." in raw:
        raw = ""

    name = Path(raw).name if raw else ""
    if not name or not name.endswith(".py"):
        name = default_name

    stem = re.sub(r"[^a-zA-Z0-9_.-]+", "_", name)
    if not stem.startswith("test_"):
        stem = default_name

    out_file = (tests_dir / stem).resolve()
    try:
        out_file.relative_to(tests_dir)
    except ValueError:
        out_file = (tests_dir / default_name).resolve()

    try:
        return str(out_file.relative_to(repo_root)).replace("\\", "/")
    except ValueError:
        return str(out_file)


def resolve_matrix_csv_path(ticket_id: str, target_framework_path: str) -> str:
    """
    Resolve where to save the generated test matrix CSV.
    """
    fw = Path(target_framework_path).expanduser().resolve()
    out_dir = (fw / "artifacts").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_ticket = re.sub(r"[^a-zA-Z0-9]+", "_", ticket_id).strip("_").lower() or "ticket"
    out_file = out_dir / f"{safe_ticket}_test_matrix.csv"
    return str(out_file)


def resolve_test_matrix_csv_path(ticket_id: str, target_framework_path: str) -> Path:
    """Same destination as ``resolve_matrix_csv_path``; returns a ``Path`` for matrix writes."""
    return Path(resolve_matrix_csv_path(ticket_id, target_framework_path))
