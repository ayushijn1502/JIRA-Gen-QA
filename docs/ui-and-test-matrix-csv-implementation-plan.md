# JiraGen-QA — Single-File Implementation Plan (UI + Test Matrix CSV)

**Purpose:** Hand this **one** Markdown file to Cursor with **Composer 2** to re-implement the same behavior as the current repository: **single overall progress percentage**, **test-case matrix CSV generation** (prompt + normalization), **CSV preview in the UI**, and **CSV download**.

**How to execute (Composer 2):**

1. Open this repository in Cursor.
2. Paste this entire file into the agent context (or attach it).
3. Instruct: *Implement by replacing the listed files with the contents in the appendices verbatim. Do not change strings, colors, layout order, or formulas unless fixing a merge conflict. Then write `docs/test_matrix.md` from Appendix D.*
4. Run `python -m py_compile gui_app.py autotest_agent/agents/prompts.py autotest_agent/agents/nodes.py` and launch `python gui_app.py` for a smoke check.

**Truth source:** Appendices **A–D** are copies of the canonical files/snippets from the repo at the time this plan was generated. If the repo drifted, prefer the appendices when reproducing this design. **Section 1a** embeds the full UI/CSV product spec (same content as the former standalone spec doc).

---

## 1. Scope (what this plan covers)

| Area | Behavior |
|------|----------|
| **Progress** | One `QProgressBar` (`pipelineTopBar`, range `0..1000`) for the full pipeline; percentage label `int(100 * (idx + 1) / N)` for stage index `idx` and `N = len(PIPELINE_STEPS)`; current stage title + description from `PIPELINE_STEPS`. |
| **Test matrix CSV** | LLM returns `TestMatrixDocument` JSON; `build_test_matrix_prompt()` loads `docs/test_matrix.md` + hard constraints; `_normalize_test_matrix_rows` before write; CSV headers fixed. |
| **CSV preview** | `QTableWidget` in JIRA card, above action row; populated from disk on `csv_ready` signal. |
| **Download** | `shutil.copy2` to user-chosen path from `_last_csv_path`. |

---

## 1a. Product spec (formerly a separate doc)

The following text is the full **UI Progress and CSV Preview** specification, merged here so you only need **this** file for product intent plus implementation.

## Objective

Update the desktop UI in this repository so the run screen:

1. shows one overall pipeline progress bar instead of an order-flow timeline or one bar per step
2. previews the generated CSV in the same screen before the user downloads it

**Test matrix CSV quality:** matrix rows must have proper, non-empty values in every column (especially `testcase`). Rules are **Appendix D**; prompt builder and normalization are **Appendix B** and **Appendix C**.

This spec is written for the current repository state and should be implementable without additional product clarification.

## Repository Scope

### Primary file

- `gui_app.py`

### Supporting files already involved in the flow

- `main.py`
- `autotest_agent/agents/nodes.py` (matrix CSV write + row normalization)
- `autotest_agent/agents/prompts.py` (`build_test_matrix_prompt`)
- `docs/test_matrix.md` (matrix CSV prompt rules; **Appendix D** in this plan)

## Current System Context

The GUI is a PySide6 desktop application.

The run flow already provides:

- stage updates through `on_stage`
- CSV-ready notification through `on_matrix_csv`
- a generated CSV file path that the UI can read from disk

The backend callback contract does not need to change for this feature.

## Required UI Changes

### 1. Replace the old progress presentation

The progress area must no longer show:

- a vertical order-style timeline
- connector lines between steps
- one progress bar per step

The progress area must now show:

- one shared progress bar for the full pipeline
- one current stage title
- one current stage description
- one overall percentage label

### 2. Progress behavior

The progress model must remain stage-based, not live within-step progress.

The percentage must be calculated from the current stage index in `PIPELINE_STEPS`.

Expected behavior:

- before the run starts: `0%`
- as each stage is reached: percentage increases based on stage position
- when the pipeline completes: `100%`
- on error: keep the bar at the last reached stage and show the error state in the stage text

The UI must continue using the existing `PIPELINE_STEPS` order in `gui_app.py`.

### 3. Current stage display

Below the shared progress bar, the UI must display:

- the current stage title
- the current stage description
- the overall percentage text

Expected state text behavior:

- idle state: a neutral message like "No run started yet"
- active state: show the matched title and description from `PIPELINE_STEPS`
- done state: show a completion message
- error state: show an error message using the last known failure summary

### 4. CSV preview section

A CSV preview section must appear in the JIRA ticket card, above the action row that contains:

- status text
- `Download CSV`
- `Run pipeline`

The preview section must include:

- a section title
- helper text for empty or reset state
- a scrollable table preview of the generated CSV

### 5. CSV preview behavior

When `_on_csv_ready()` receives a path:

- store the path in `_last_csv_path`
- enable the `Download CSV` button
- read the CSV from disk
- populate the preview table using the CSV headers and rows

The UI must handle these cases gracefully:

- file path missing
- file no longer exists
- CSV cannot be opened
- CSV exists but has no rows
- uneven row lengths

For uneven rows, blank values may be shown in missing cells.

### 6. Reset behavior

When a new run starts in `_on_start()`:

- clear `_last_csv_path`
- disable `Download CSV`
- clear the CSV preview table
- restore the preview helper text
- reset the progress bar to `0%`
- reset the current stage title and description to the idle state

## Non-Goals

This spec does not require:

- backend progress percentages inside individual long-running stages
- new stage callback types
- changes to the CLI output format
- CSV editing in the UI
- pagination for the CSV preview
- new automated tests

## Implementation Notes

### `gui_app.py`

Implementation is expected to be centered in `MainWindow`.

Relevant areas:

- `PIPELINE_STEPS`
- progress card layout
- `_update_pipeline_top_bar()`
- `_apply_pipeline_stage()`
- `_on_csv_ready()`
- `_on_start()`
- `_download_csv()`

Recommended implementation shape:

1. keep the existing top pipeline bar widget
2. replace the old step timeline widgets with one current-stage summary block
3. add a CSV preview widget in the ticket section
4. add a helper method to clear the preview state
5. add a helper method to load and render CSV data from disk

### `main.py`

No functional change is required unless a small status-text adjustment is needed.

### `autotest_agent/agents/nodes.py`

- `matrix_csv` must continue to call `on_matrix_csv` with the absolute CSV path after write.
- After the LLM returns `TestMatrixDocument`, normalize each row (strip whitespace, ensure non-empty fields, sensible fallback `testcase` with ticket id) before writing CSV so exported files and the GUI preview stay consistent.

## Acceptance Criteria

This change is complete only if all of the following are true:

1. The progress section shows one overall progress bar only.
2. The old vertical timeline or per-step progress cards are no longer visible.
3. The current stage title, description, and percentage update as the pipeline advances.
4. The percentage reaches `100%` on successful completion.
5. The CSV preview appears automatically after the matrix CSV is generated.
6. The CSV preview appears before the `Download CSV` button in the layout.
7. The CSV preview content matches the generated CSV file.
8. Starting a new run clears the old CSV preview and disables download until a new CSV is available.
9. The existing `Download CSV` action still saves the same CSV shown in the preview.

## Manual Validation

Use this checklist after implementation:

1. Launch the GUI from the repository.
2. Confirm the progress area shows only one shared progress bar.
3. Start a run and confirm the percentage changes as stages are reached.
4. Confirm the stage title and description change with the active stage.
5. Confirm the CSV preview appears once the matrix CSV is created.
6. Confirm the preview still allows the CSV to be downloaded.
7. Start another run and confirm the old preview is cleared before new output arrives.
8. Trigger or observe an error path and confirm the UI keeps the last known percentage while showing an error message.

## Developer Handoff

If another developer implements this spec, they should be able to complete the work by primarily editing `gui_app.py` and then validating the flow manually through the desktop app.

---

## 2. Backend stage contract (`main.py` → GUI)

`execute_run(..., on_stage=..., on_matrix_csv=...)` emits `on_stage` in this order before the graph:

- `started`, `settings`, `gemini_check`, `indexing`, `jira_fetch`

The graph (`NodeContainer`) emits via `on_stage` (see nodes for analyze, matrix_csv, generate, verify, deploy).

After success, `execute_run` calls `on_stage("done")`. On exception, `on_stage("error")`.

`NodeContainer.matrix_csv` calls `on_matrix_csv(abs_path)` with the **absolute** path to the written CSV.

**GUI must wire:** `pipeline_stage` → `_apply_pipeline_stage`, `csv_ready` → `_on_csv_ready`, and pass both into `execute_run` from `RunWorker.run()`.

---

## 3. `PIPELINE_STEPS` (must match `gui_app.py` Appendix A)

Same 10 tuples as in `gui_app.py`: `started`, `settings`, `gemini_check`, `indexing`, `jira_fetch`, `analyze`, `matrix_csv`, `generate`, `verify`, `deploy` — with titles and descriptions exactly as in Appendix A.

---

## 4. CSV file format

- **Path:** `resolve_test_matrix_csv_path` in `autotest_agent/infrastructure/output_paths.py` (not duplicated here; keep existing project helper).
- **Headers (exact):** `testcase`, `Description`, `PreCondition`, `TestSteps`, `Expected Results`
- **JSON keys from LLM (snake_case):** `testcase`, `description`, `precondition`, `test_steps`, `expected_results`

---

## 5. Embedded rules file (`docs/test_matrix.md`)

The runtime prompt loads this from disk. Appendix **D** is the full file to write.

---

## 6. `nodes.py` changes (matrix only)

Appendix **C** contains:

- `def _normalize_test_matrix_rows(...)` (module level)
- full `def matrix_csv(self, state: GraphState) -> dict[str, Any]:` through its return

Integrate into the existing `NodeContainer` class in `autotest_agent/agents/nodes.py` (preserve imports: `csv`, `TestMatrixDocument`, `TestMatrixRow`, `resolve_test_matrix_csv_path`, etc.). If your file already has a different `matrix_csv`, replace that method and add `_normalize_test_matrix_rows` if missing.

---

## 7. Acceptance checklist

- [ ] Only one slim progress bar in the progress card; no per-step bars, no timeline.
- [ ] Percent and bar advance at each `PIPELINE_STEPS` stage; `done` → 100% / full bar; `error` → red copy + last segment percent.
- [ ] CSV preview hidden until path received; table matches file.
- [ ] New run clears preview, disables download until new CSV.
- [ ] Download copies the same file as preview.
- [ ] Matrix CSV: no empty cells after normalization; testcase column sensible.

---

## Appendix A — `gui_app.py` (full file, verbatim)

```python
"""Qt (PySide6) desktop launcher for AutoTest-Agent `run` — web-inspired UI."""

from __future__ import annotations

import csv
import os
import re
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import (
    Q_ARG,
    QMetaObject,
    QObject,
    Qt,
    QThread,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QFont,
    QFontDatabase,
    QPalette,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from rich.text import Text

from main import execute_run

# Web-like dark theme (elevated surfaces, soft borders — Linear/Vercel-adjacent)
_BG_CANVAS = "#09090b"
_BG_SURFACE = "#12121a"
_BG_ELEVATED = "#18181f"
_BG_INPUT = "#1c1c26"
_BG_LOG = "#0c0c12"
_FG = "#fafafa"
_FG_MUTED = "#a1a1aa"
_BORDER = "#27272a"
_BORDER_SUBTLE = "#3f3f46"
_ACCENT = "#6366f1"
_ACCENT_SOFT = "#818cf8"
_PRIMARY_BG = "#22c55e"
_PRIMARY_HOVER = "#16a34a"
_PRIMARY_DIM = "#14532d"
_LOG_ERR = "#f87171"

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[mK]|\x1b\][^\x07]*\x07|\x1b\]8;;[^\x1b]*\x1b\\")

# (stage_id, title, description — shown like order-tracking subtitle; tooltip = same + errors)
PIPELINE_STEPS: list[tuple[str, str, str]] = [
    ("started", "Run starting", "Prepare the environment and load configuration."),
    ("settings", "Settings loaded", "Your config.yaml was read and validated."),
    ("gemini_check", "AI connection", "Optional check that your Gemini API key works."),
    ("indexing", "Code indexed", "Scan the target repository for RAG context."),
    ("jira_fetch", "Ticket loaded", "Pull title, description, and criteria from JIRA."),
    ("analyze", "Ticket understood", "Map the ticket and codebase into a test plan."),
    ("matrix_csv", "Test matrix ready", "Generate the CSV matrix before automation."),
    ("generate", "Tests written", "Create pytest code aligned with the matrix."),
    ("verify", "Checks run", "Run pytest and retry fixes when needed."),
    ("deploy", "Ready to publish", "Approve and open a pull request if configured."),
]


def _strip_ansi(s: str) -> str:
    return _ANSI_ESCAPE.sub("", s)


def _app_stylesheet() -> str:
    return f"""
    QMainWindow {{
        background-color: {_BG_CANVAS};
    }}
    QWidget#centralRoot {{
        background-color: {_BG_CANVAS};
        color: {_FG};
    }}
    QFrame#topBar {{
        background-color: {_BG_SURFACE};
        border: none;
        border-bottom: 1px solid {_BORDER};
    }}
    QLabel#brandTitle {{
        color: {_FG};
        font-size: 15pt;
        font-weight: 700;
        letter-spacing: -0.5px;
        background: transparent;
    }}
    QLabel#topTag {{
        color: {_FG_MUTED};
        font-size: 10pt;
        font-weight: 500;
        background: transparent;
    }}
    QScrollArea {{
        border: none;
        background-color: {_BG_CANVAS};
    }}
    QWidget#scrollInner {{
        background-color: {_BG_CANVAS};
    }}
    QLabel {{
        color: {_FG};
        background: transparent;
    }}
    QLabel#hero {{
        color: {_FG};
        font-size: 26pt;
        font-weight: 800;
        letter-spacing: -1px;
        background: transparent;
    }}
    QLabel#heroHint {{
        color: {_ACCENT_SOFT};
        font-size: 11pt;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        background: transparent;
    }}
    QLabel#subtitle {{
        color: {_FG_MUTED};
        font-size: 11pt;
        line-height: 1.5;
        background: transparent;
    }}
    QLabel#sectionTitle {{
        color: {_FG};
        font-size: 12pt;
        font-weight: 700;
        letter-spacing: -0.3px;
        background: transparent;
        padding-bottom: 4px;
    }}
    QLabel#fieldLabel {{
        color: {_FG_MUTED};
        font-size: 10pt;
        font-weight: 600;
        background: transparent;
    }}
    QLabel#hint {{
        color: {_FG_MUTED};
        font-size: 9pt;
        background: transparent;
    }}
    QLabel#status {{
        color: {_FG_MUTED};
        font-size: 10pt;
        background: transparent;
        padding: 8px 14px;
    }}
    QFrame#card {{
        background-color: {_BG_ELEVATED};
        border: 1px solid {_BORDER};
        border-radius: 14px;
    }}
    QLineEdit {{
        background-color: {_BG_INPUT};
        color: {_FG};
        border: 1px solid {_BORDER};
        border-radius: 10px;
        padding: 12px 14px;
        font-size: 11pt;
        selection-background-color: {_ACCENT};
        selection-color: #ffffff;
    }}
    QLineEdit:hover {{
        border: 1px solid {_BORDER_SUBTLE};
    }}
    QLineEdit:focus {{
        border: 2px solid {_ACCENT};
        padding: 11px 13px;
    }}
    QPushButton#ghost {{
        background-color: transparent;
        color: {_ACCENT_SOFT};
        border: 1px solid {_BORDER};
        border-radius: 10px;
        padding: 10px 18px;
        font-size: 10pt;
        font-weight: 600;
    }}
    QPushButton#ghost:hover {{
        background-color: {_BG_INPUT};
        border-color: {_BORDER_SUBTLE};
        color: {_FG};
    }}
    QPushButton#ghost:pressed {{
        background-color: {_BG_SURFACE};
    }}
    QPushButton#secondary {{
        background-color: {_BG_INPUT};
        color: {_FG};
        border: 1px solid {_BORDER};
        border-radius: 10px;
        padding: 10px 20px;
        font-size: 10pt;
        font-weight: 600;
    }}
    QPushButton#secondary:hover {{
        border-color: {_ACCENT_SOFT};
    }}
    QPushButton#secondary:disabled {{
        color: #71717a;
        border-color: #3f3f46;
    }}
    QPushButton#primary {{
        background-color: {_PRIMARY_BG};
        color: #ffffff;
        border: none;
        border-radius: 999px;
        padding: 12px 28px;
        font-size: 11pt;
        font-weight: 700;
    }}
    QPushButton#primary:hover {{
        background-color: {_PRIMARY_HOVER};
    }}
    QPushButton#primary:pressed {{
        background-color: {_PRIMARY_DIM};
    }}
    QPushButton#primary:disabled {{
        background-color: #3f3f46;
        color: #71717a;
    }}
    QFrame#pipelineTrack {{
        background-color: {_BG_SURFACE};
        border: 1px solid {_BORDER};
        border-radius: 16px;
    }}
    QLabel#stepTitle {{
        color: {_FG};
        font-size: 12pt;
        font-weight: 700;
        letter-spacing: -0.3px;
        background: transparent;
    }}
    QLabel#stepDesc {{
        color: {_FG_MUTED};
        font-size: 10pt;
        font-weight: 400;
        line-height: 1.45;
        background: transparent;
    }}
    QLabel#stepPercent {{
        color: {_FG_MUTED};
        font-size: 10pt;
        font-weight: 700;
        background: transparent;
    }}
    QLabel#csvPreviewTitle {{
        color: {_FG};
        font-size: 10pt;
        font-weight: 700;
        background: transparent;
    }}
    QTableWidget {{
        background-color: {_BG_INPUT};
        color: {_FG};
        border: 1px solid {_BORDER};
        border-radius: 12px;
        gridline-color: {_BORDER};
        selection-background-color: #312e81;
        selection-color: #ffffff;
    }}
    QHeaderView::section {{
        background-color: {_BG_SURFACE};
        color: {_FG};
        border: none;
        border-bottom: 1px solid {_BORDER};
        padding: 8px 10px;
        font-weight: 700;
    }}
    QScrollBar:vertical {{
        background: {_BG_LOG};
        width: 10px;
        border-radius: 5px;
        margin: 4px 2px 4px 0;
    }}
    QScrollBar::handle:vertical {{
        background: {_BORDER_SUBTLE};
        border-radius: 5px;
        min-height: 36px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: #52525b;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
        border: none;
    }}
    QScrollBar:horizontal {{
        height: 0;
    }}
    QProgressBar#pipelineTopBar {{
        border: none;
        background-color: #27272a;
        border-radius: 999px;
        min-height: 5px;
        max-height: 5px;
    }}
    QProgressBar#pipelineTopBar::chunk {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {_ACCENT}, stop:1 {_ACCENT_SOFT});
        border-radius: 999px;
    }}
    """


def _apply_ui_font(app: QApplication) -> None:
    preferred = [
        "Inter",
        "Segoe UI Variable",
        "Segoe UI",
        ".AppleSystemUIFont",
        "SF Pro Text",
        "Helvetica Neue",
        "Arial",
    ]
    for name in preferred:
        if name in QFontDatabase.families():
            f = QFont(name)
            f.setPointSize(10)
            app.setFont(f)
            return
    f = QFont()
    f.setPointSize(10)
    app.setFont(f)


class RunWorker(QObject):
    """Runs ``execute_run`` on a ``QThread``; forwards stages and status to the GUI thread."""

    finished = Signal()
    pipeline_stage = Signal(str)
    csv_ready = Signal(str)
    status_message = Signal(str, str)

    def __init__(
        self,
        ticket_id: str,
        text_input: Callable[[str], str],
    ) -> None:
        super().__init__()
        self._ticket_id = ticket_id
        self._text_input = text_input

    @Slot()
    def run(self) -> None:
        def user_log(level: str, msg: str) -> None:
            self.status_message.emit(level, msg)

        try:
            execute_run(
                self._ticket_id,
                "config.yaml",
                user_log=user_log,
                text_input=self._text_input,
                on_stage=self.pipeline_stage.emit,
                on_matrix_csv=self.csv_ready.emit,
            )
        finally:
            self.finished.emit()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AutoTest-Agent")
        self.setMinimumSize(880, 720)
        self.resize(980, 820)
        self._thread: QThread | None = None
        self._worker: RunWorker | None = None
        self._approval_last = "n"
        self._current_stage_index = -1
        self._last_csv_path: str | None = None
        self._last_pipeline_error = ""

        root = QWidget()
        root.setObjectName("centralRoot")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        top = QFrame()
        top.setObjectName("topBar")
        top_lay = QHBoxLayout(top)
        top_lay.setContentsMargins(28, 18, 28, 18)
        brand = QLabel("AutoTest-Agent")
        brand.setObjectName("brandTitle")
        top_lay.addWidget(brand)
        top_lay.addStretch()
        tag = QLabel("JIRA  →  Matrix CSV  →  Automation  →  GitHub")
        tag.setObjectName("topTag")
        top_lay.addWidget(tag)
        outer.addWidget(top)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        scroll_inner = QWidget()
        scroll_inner.setObjectName("scrollInner")
        content = QVBoxLayout(scroll_inner)
        content.setContentsMargins(40, 32, 40, 36)
        content.setSpacing(0)

        kicker = QLabel("Pipeline")
        kicker.setObjectName("heroHint")
        content.addWidget(kicker)

        hero = QLabel("Generate tests from JIRA")
        hero.setObjectName("hero")
        content.addWidget(hero)

        sub = QLabel(
            "Uses config.yaml in this folder. Progress is shown through one overall pipeline bar, "
            "and the generated matrix CSV is previewed in the same screen before download."
        )
        sub.setObjectName("subtitle")
        sub.setWordWrap(True)
        content.addWidget(sub)
        content.addSpacing(20)

        cfg_card = QFrame()
        cfg_card.setObjectName("card")
        cfg_outer = QVBoxLayout(cfg_card)
        cfg_outer.setContentsMargins(24, 22, 24, 22)
        cfg_outer.setSpacing(16)

        sec_cfg = QLabel("JIRA ticket")
        sec_cfg.setObjectName("sectionTitle")
        cfg_outer.addWidget(sec_cfg)

        cfg_grid = QGridLayout()
        cfg_grid.setSpacing(10)
        cfg_grid.setColumnStretch(0, 1)

        jl = QLabel("Ticket ID")
        jl.setObjectName("fieldLabel")
        cfg_grid.addWidget(jl, 0, 0)
        self._ticket = QLineEdit()
        self._ticket.setPlaceholderText("e.g. PROJ-123")
        cfg_grid.addWidget(self._ticket, 1, 0)

        hint = QLabel(
            "Board key and number (example: SCRUM-42). Run the pipeline to update step progress and preview the CSV output."
        )
        hint.setObjectName("hint")
        cfg_grid.addWidget(hint, 2, 0)

        cfg_outer.addLayout(cfg_grid)
        cfg_outer.addSpacing(8)

        csv_preview = QFrame()
        csv_preview.setObjectName("pipelineTrack")
        csv_preview_lay = QVBoxLayout(csv_preview)
        csv_preview_lay.setContentsMargins(20, 18, 20, 20)
        csv_preview_lay.setSpacing(12)

        csv_title = QLabel("CSV preview")
        csv_title.setObjectName("csvPreviewTitle")
        csv_preview_lay.addWidget(csv_title)

        self._csv_preview_hint = QLabel(
            "The generated matrix will appear here as soon as the CSV step finishes."
        )
        self._csv_preview_hint.setObjectName("hint")
        self._csv_preview_hint.setWordWrap(True)
        csv_preview_lay.addWidget(self._csv_preview_hint)

        self._csv_preview_table = QTableWidget(0, 0)
        self._csv_preview_table.setAlternatingRowColors(True)
        self._csv_preview_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._csv_preview_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._csv_preview_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._csv_preview_table.verticalHeader().setVisible(False)
        self._csv_preview_table.horizontalHeader().setStretchLastSection(True)
        self._csv_preview_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._csv_preview_table.setMinimumHeight(190)
        self._csv_preview_table.setVisible(False)
        csv_preview_lay.addWidget(self._csv_preview_table)

        cfg_outer.addWidget(csv_preview)

        action_row = QHBoxLayout()
        action_row.setSpacing(12)
        self._status = QLabel("Ready — enter a ticket, then run.")
        self._status.setObjectName("status")
        self._status.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        action_row.addWidget(self._status, stretch=1)

        self._download_btn = QPushButton("Download CSV")
        self._download_btn.setObjectName("secondary")
        self._download_btn.setEnabled(False)
        self._download_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._download_btn.clicked.connect(self._download_csv)
        action_row.addWidget(self._download_btn)

        self._start = QPushButton("Run pipeline")
        self._start.setObjectName("primary")
        self._start.setCursor(Qt.CursorShape.PointingHandCursor)
        self._start.clicked.connect(self._on_start)
        action_row.addWidget(self._start)
        cfg_outer.addLayout(action_row)

        content.addWidget(cfg_card)
        content.addSpacing(20)

        progress_card = QFrame()
        progress_card.setObjectName("card")
        prog_outer = QVBoxLayout(progress_card)
        prog_outer.setContentsMargins(24, 22, 24, 22)
        prog_outer.setSpacing(16)

        sec_prog = QLabel("Pipeline progress")
        sec_prog.setObjectName("sectionTitle")
        prog_outer.addWidget(sec_prog)

        self._pipeline_top_bar = QProgressBar()
        self._pipeline_top_bar.setObjectName("pipelineTopBar")
        self._pipeline_top_bar.setTextVisible(False)
        self._pipeline_top_bar.setRange(0, 1000)
        self._pipeline_top_bar.setValue(0)
        self._pipeline_top_bar.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        prog_outer.addWidget(self._pipeline_top_bar)

        track = QFrame()
        track.setObjectName("pipelineTrack")
        track_lay = QVBoxLayout(track)
        track_lay.setContentsMargins(20, 18, 20, 20)
        track_lay.setSpacing(14)

        track_hint = QLabel(
            "The bar below tracks the overall pipeline progress from start to publish. "
            "Current stage details update as the run moves forward."
        )
        track_hint.setObjectName("hint")
        track_hint.setWordWrap(True)
        track_lay.addWidget(track_hint)

        current_row = QHBoxLayout()
        current_row.setSpacing(12)

        current_wrap = QWidget()
        current_lay = QVBoxLayout(current_wrap)
        current_lay.setContentsMargins(0, 0, 0, 0)
        current_lay.setSpacing(4)

        self._current_step_title = QLabel("No run started yet")
        self._current_step_title.setObjectName("stepTitle")
        current_lay.addWidget(self._current_step_title)

        self._current_step_desc = QLabel(
            "Start the pipeline to begin tracking progress across all steps."
        )
        self._current_step_desc.setObjectName("stepDesc")
        self._current_step_desc.setWordWrap(True)
        current_lay.addWidget(self._current_step_desc)

        self._current_step_percent = QLabel("0%")
        self._current_step_percent.setObjectName("stepPercent")
        self._current_step_percent.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        current_row.addWidget(current_wrap, 1)
        current_row.addWidget(self._current_step_percent, 0, alignment=Qt.AlignmentFlag.AlignTop)
        track_lay.addLayout(current_row)
        prog_outer.addWidget(track)
        content.addWidget(progress_card)
        content.addStretch(1)

        scroll.setWidget(scroll_inner)
        outer.addWidget(scroll)

        self._centered = False

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        if not self._centered:
            self._centered = True
            geo = self.frameGeometry()
            center = self.screen().availableGeometry().center()
            geo.moveCenter(center)
            self.move(geo.topLeft())

    def focus_ticket_field(self) -> None:
        self._ticket.setFocus()

    @Slot(str)
    def _approval_dialog_slot(self, body: str) -> None:
        r = QMessageBox.question(
            self,
            "Approve",
            body,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        self._approval_last = "y" if r == QMessageBox.StandardButton.Yes else "n"

    def _make_text_input(self) -> Callable[[str], str]:
        def _ask(prompt: str) -> str:
            try:
                body = Text.from_markup(prompt, emoji=False).plain
            except Exception:
                body = prompt
            body = _strip_ansi(body).strip()
            body = (
                f"{body}\n\n"
                "Yes — approve and continue\n"
                "No — cancel the run"
            )
            QMetaObject.invokeMethod(
                self,
                "_approval_dialog_slot",
                Qt.ConnectionType.BlockingQueuedConnection,
                Q_ARG(str, body),
            )
            return self._approval_last

        return _ask

    def _update_pipeline_top_bar(self, reveal_idx: int) -> None:
        n = len(PIPELINE_STEPS)
        if reveal_idx < 0:
            self._pipeline_top_bar.setValue(0)
        else:
            self._pipeline_top_bar.setValue(
                max(0, min(1000, int(1000 * (reveal_idx + 1) / n)))
            )

    def _set_current_step_display(
        self,
        *,
        title: str,
        description: str,
        percent_text: str,
        title_color: str = _FG,
        desc_color: str = _FG_MUTED,
        percent_color: str = _FG_MUTED,
    ) -> None:
        self._current_step_title.setText(title)
        self._current_step_desc.setText(description)
        self._current_step_percent.setText(percent_text)
        self._current_step_title.setStyleSheet(
            f"color: {title_color}; font-size: 12pt; font-weight: 700; letter-spacing: -0.3px;"
        )
        self._current_step_desc.setStyleSheet(
            f"color: {desc_color}; font-size: 10pt; font-weight: 400; line-height: 1.45;"
        )
        self._current_step_percent.setStyleSheet(
            f"color: {percent_color}; font-size: 10pt; font-weight: 800; background: transparent;"
        )

    def _clear_csv_preview(self, message: str) -> None:
        self._csv_preview_hint.setText(message)
        self._csv_preview_hint.setVisible(True)
        self._csv_preview_table.clear()
        self._csv_preview_table.setRowCount(0)
        self._csv_preview_table.setColumnCount(0)
        self._csv_preview_table.setVisible(False)

    def _load_csv_preview(self, path: str) -> None:
        src = Path(path)
        if not src.is_file():
            self._clear_csv_preview("The generated CSV could not be found on disk.")
            return
        try:
            with src.open("r", encoding="utf-8", newline="") as fh:
                rows = list(csv.reader(fh))
        except OSError:
            self._clear_csv_preview("The CSV could not be opened for preview.")
            return

        if not rows:
            self._clear_csv_preview("The CSV was created, but it is empty.")
            return

        headers = rows[0]
        data_rows = rows[1:]
        self._csv_preview_table.clear()
        self._csv_preview_table.setColumnCount(len(headers))
        self._csv_preview_table.setHorizontalHeaderLabels(headers)
        self._csv_preview_table.setRowCount(len(data_rows))

        for row_idx, row in enumerate(data_rows):
            for col_idx in range(len(headers)):
                value = row[col_idx] if col_idx < len(row) else ""
                item = QTableWidgetItem(value)
                self._csv_preview_table.setItem(row_idx, col_idx, item)

        self._csv_preview_table.resizeColumnsToContents()
        self._csv_preview_hint.setText(
            f"Previewing {len(data_rows)} row(s) from {src.name}."
        )
        self._csv_preview_hint.setVisible(True)
        self._csv_preview_table.setVisible(True)

    def _reset_pipeline_visual(self) -> None:
        self._current_stage_index = -1
        self._update_pipeline_top_bar(-1)
        self._set_current_step_display(
            title="No run started yet",
            description="Start the pipeline to begin tracking progress across all steps.",
            percent_text="0%",
        )

    @Slot(str)
    def _apply_pipeline_stage(self, stage_id: str) -> None:
        if stage_id == "error":
            detail = (self._last_pipeline_error or "").strip() or (
                "The pipeline stopped due to an error. Check the status line above."
            )
            self._status.setText("Something went wrong — check the status line and details above.")
            self._update_pipeline_top_bar(max(0, self._current_stage_index))
            self._set_current_step_display(
                title="Pipeline stopped",
                description=detail,
                percent_text=(
                    "0%"
                    if self._current_stage_index < 0
                    else f"{int(100 * (self._current_stage_index + 1) / len(PIPELINE_STEPS))}%"
                ),
                title_color=_LOG_ERR,
                desc_color=_LOG_ERR,
                percent_color=_LOG_ERR,
            )
            return
        if stage_id == "done":
            self._update_pipeline_top_bar(len(PIPELINE_STEPS) - 1)
            self._status.setText("Pipeline complete. Download the CSV if you need a copy.")
            self._set_current_step_display(
                title="Pipeline complete",
                description="All pipeline steps finished. Review the CSV preview or download the file if needed.",
                percent_text="100%",
                title_color=_PRIMARY_BG,
                percent_color=_PRIMARY_BG,
            )
            return
        try:
            idx = next(i for i, (sid, _, _) in enumerate(PIPELINE_STEPS) if sid == stage_id)
        except StopIteration:
            return
        self._current_stage_index = idx
        self._update_pipeline_top_bar(idx)
        _sid, title, desc = PIPELINE_STEPS[idx]
        self._set_current_step_display(
            title=title,
            description=desc,
            percent_text=f"{int(100 * (idx + 1) / len(PIPELINE_STEPS))}%",
            title_color=_ACCENT_SOFT,
            percent_color=_ACCENT_SOFT,
        )

    @Slot(str, str)
    def _on_status_message(self, level: str, msg: str) -> None:
        lvl = (level or "INFO").upper()
        if lvl == "ERROR":
            self._last_pipeline_error = msg
        prefix = {
            "INFO": "",
            "SUCCESS": "✓ ",
            "WARN": "⚠ ",
            "WARNING": "⚠ ",
            "ERROR": "Error: ",
        }.get(lvl, "")
        self._status.setText(f"{prefix}{msg}")

    @Slot(str)
    def _on_csv_ready(self, path: str) -> None:
        self._last_csv_path = path
        self._download_btn.setEnabled(True)
        self._load_csv_preview(path)

    def _download_csv(self) -> None:
        if not self._last_csv_path:
            return
        src = Path(self._last_csv_path)
        if not src.is_file():
            QMessageBox.warning(self, "AutoTest-Agent", "The matrix file is no longer on disk.")
            return
        dest, _ = QFileDialog.getSaveFileName(
            self,
            "Save test matrix CSV",
            src.name,
            "CSV (*.csv);;All files (*.*)",
        )
        if dest:
            shutil.copy2(src, dest)
            QMessageBox.information(self, "Saved", f"Saved to:\n{dest}")

    def _on_start(self) -> None:
        if not self._start.isEnabled():
            return
        if self._thread is not None and self._thread.isRunning():
            return
        tid = self._ticket.text().strip()
        if not tid:
            QMessageBox.warning(
                self,
                "AutoTest-Agent",
                "Please enter a JIRA ticket ID (for example PROJ-123).",
            )
            return

        self._last_csv_path = None
        self._download_btn.setEnabled(False)
        self._last_pipeline_error = ""
        self._clear_csv_preview(
            "The generated matrix will appear here as soon as the CSV step finishes."
        )
        self._reset_pipeline_visual()

        self._start.setEnabled(False)
        self._status.setText("Starting pipeline…")

        self._thread = QThread()
        self._worker = RunWorker(tid, self._make_text_input())
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.pipeline_stage.connect(self._apply_pipeline_stage)
        self._worker.csv_ready.connect(self._on_csv_ready)
        self._worker.status_message.connect(self._on_status_message)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.start()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._thread is not None and self._thread.isRunning():
            QMessageBox.information(
                self,
                "Run in progress",
                "Please wait until the current run finishes before closing the window.",
            )
            event.ignore()
            return
        super().closeEvent(event)

    @Slot()
    def _on_thread_finished(self) -> None:
        self._start.setEnabled(True)
        self._status.setText("Ready — enter a ticket, then run.")
        th = self._thread
        self._thread = None
        self._worker = None
        if th is not None:
            th.deleteLater()


def _ensure_qt_platform_plugins() -> None:
    """
    Avoid macOS error: Could not find the Qt platform plugin "cocoa" in ""

    Blank ``QT_PLUGIN_PATH`` / ``QT_QPA_PLATFORM_PLUGIN_PATH`` values make Qt search
    nowhere. That can come from an IDE "Run" configuration or a parent process even
    when your shell has no ``QT_*`` entries — so we always pin PySide6's bundled
    ``.../plugins`` directory (must contain a ``platforms/`` subfolder) before
    ``QApplication`` is constructed.
    """
    for key in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"):
        val = os.environ.get(key)
        if val is not None and not val.strip():
            del os.environ[key]

    try:
        import PySide6
    except ImportError:
        return

    pkg = Path(PySide6.__file__).resolve().parent
    candidates = [
        pkg / "Qt" / "plugins",
        pkg / "plugins",
    ]
    plugins_root: Path | None = None
    for c in candidates:
        if c.is_dir() and (c / "platforms").is_dir():
            plugins_root = c
            break

    if plugins_root is None:
        return

    os.environ["QT_PLUGIN_PATH"] = str(plugins_root)


def _apply_dark_fusion(app: QApplication) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(_BG_CANVAS))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(_FG))
    pal.setColor(QPalette.ColorRole.Base, QColor(_BG_INPUT))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(_BG_ELEVATED))
    pal.setColor(QPalette.ColorRole.Text, QColor(_FG))
    pal.setColor(QPalette.ColorRole.Button, QColor(_BG_ELEVATED))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(_FG))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(_ACCENT))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(pal)
    app.setStyleSheet(_app_stylesheet())


def main() -> None:
    _ensure_qt_platform_plugins()
    if sys.platform == "darwin":
        import multiprocessing

        try:
            multiprocessing.set_start_method("spawn", force=False)
        except RuntimeError:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName("AutoTest-Agent")
    app.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    _apply_ui_font(app)
    _apply_dark_fusion(app)
    win = MainWindow()
    win.show()
    win.focus_ticket_field()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()

```

---

## Appendix B — `autotest_agent/agents/prompts.py` (full file, verbatim)

```python
"""
Prompt Builder -- reads the docs/*.md files and assembles system prompts
for each node in the LangGraph workflow.

Think of it as a "briefing packet" assembler: before each agent starts
its job, we hand it a packet that says "here's who you are, here are the
rules, and here's the context you need."  The content comes from the
markdown files the team maintains in /docs.

Usage:
    builder = PromptBuilder(docs_path="./docs")
    system_prompt = builder.build_analyze_prompt()
"""

from __future__ import annotations

from pathlib import Path


class PromptBuilder:
    """
    Reads markdown files from the docs/ directory once, then builds
    specialised system prompts for each workflow node on demand.
    """

    def __init__(self, docs_path: str = "./docs") -> None:
        self._docs_path = Path(docs_path)
        self._agents_md = self._read("agents.md")
        self._skills_md = self._read("skills.md")
        self._knowledge_base_md = self._read("knowledge_base.md")

    def _read(self, filename: str) -> str:
        """Read a single markdown file; return empty string if missing."""
        path = self._docs_path / filename
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def build_analyze_prompt(self) -> str:
        """
        System prompt for the Analyze node.
        Combines the JiraAnalyzer + FrameworkExpert personas with
        the skills catalogue so the LLM knows what tools it has.
        """
        return (
            "You are a senior QA analyst. Your job is to read a JIRA ticket "
            "and produce a detailed test plan.\n\n"
            "# Agent Roles\n" + self._agents_md + "\n\n"
            "# Available Skills\n" + self._skills_md + "\n\n"
            "# Rules\n" + self._knowledge_base_md
        )

    def build_generate_prompt(self) -> str:
        """
        System prompt for the Generate node.
        Gives the TestArchitect persona full access to the coding rules
        so it writes tests that match the project's style.
        """
        return (
            "You are a senior test automation engineer. Your job is to write "
            "clean, passing pytest code that follows every rule below.\n\n"
            "# Coding Standards & Rules\n" + self._knowledge_base_md + "\n\n"
            "# Agent Roles\n" + self._agents_md
        )

    def build_fix_prompt(self) -> str:
        """
        System prompt used when tests failed and we need the LLM
        to fix its own code.  Emphasises the error output and the
        coding rules it probably violated.
        """
        return (
            "You are a senior test automation engineer debugging a test failure. "
            "The previous code you generated failed pytest. "
            "Fix the code so all tests pass. "
            "Pay close attention to the error output and the coding rules.\n\n"
            "# Coding Standards & Rules\n" + self._knowledge_base_md
        )

    def build_test_matrix_prompt(self) -> str:
        """System prompt for the matrix_csv node — test case CSV before codegen."""
        matrix_rules = self._read("test_matrix.md")
        hard_constraints = (
            "\n\n# Hard constraints (do not violate)\n"
            "- Every row: all five fields are non-empty strings; use `N/A` only as allowed in the rules.\n"
            "- `testcase`: unique short title per row; include the JIRA key from the user message when possible.\n"
            "- `test_steps`: always numbered lines (1. 2. …), newline-separated.\n"
            "- Output must be a single JSON object with key `rows` only; no markdown fences.\n"
        )
        return (
            "You are a senior QA analyst. Expand the JIRA ticket and test plan into "
            "a formal test-case matrix (rows for a spreadsheet).\n\n"
            + (matrix_rules if matrix_rules else "# Rules\nProduce detailed matrix rows.\n")
            + hard_constraints
            + "\n\n# Agent Roles\n"
            + self._agents_md
        )

```

---

## Appendix C — `autotest_agent/agents/nodes.py` (excerpt: normalization + `matrix_csv` only)

Add `_normalize_test_matrix_rows` at **module level** (after `_build_failure_summary`, before `class NodeContainer`). Replace the entire `matrix_csv` method on `NodeContainer` with the method below (keep indentation as shown).

```python
def _normalize_test_matrix_rows(doc: TestMatrixDocument, ticket_id: str) -> TestMatrixDocument:
    """Strip fields and ensure non-empty CSV-safe values after LLM output."""
    cleaned: list[TestMatrixRow] = []
    for i, r in enumerate(doc.rows):
        tc = (r.testcase or "").strip() or f"{ticket_id} — Case {i + 1}"
        if len(tc) > 120:
            tc = tc[:117].rstrip() + "..."
        desc = (r.description or "").strip() or "N/A"
        pre = (r.precondition or "").strip() or "N/A"
        steps = (r.test_steps or "").strip() or "N/A"
        exp = (r.expected_results or "").strip() or "N/A"
        cleaned.append(
            TestMatrixRow(
                testcase=tc,
                description=desc,
                precondition=pre,
                test_steps=steps,
                expected_results=exp,
            )
        )
    return TestMatrixDocument(rows=cleaned)

    def matrix_csv(self, state: GraphState) -> dict[str, Any]:
        """
        Turn the ticket + test plan into a formal CSV matrix on disk.
        After this node the state has ``test_matrix_csv_path``.
        """
        ticket = state["ticket"]
        plan = state["plan"]
        self._stage("matrix_csv")
        self.console.print(
            f"\n[bold blue]Building test-case matrix CSV for {ticket.id}...[/bold blue]"
        )
        self._u(
            "INFO",
            "Creating the test-case matrix (spreadsheet-style) before writing automation…",
        )

        out_path = resolve_test_matrix_csv_path(ticket.id, self.target_framework_path)
        system_prompt = self.prompts.build_test_matrix_prompt()
        user_prompt = (
            f"JIRA Ticket: {ticket.id}\n"
            f"Title: {ticket.title}\n"
            f"Description:\n{ticket.description}\n\n"
            f"Acceptance Criteria:\n"
            + "\n".join(f"- {ac}" for ac in ticket.acceptance_criteria)
            + "\n\nTest plan from analysis:\n"
            f"Target file: {plan.target_file}\n"
            f"Scenarios:\n"
            + "\n".join(f"- {s}" for s in plan.test_scenarios)
            + "\n\nYour entire answer must be ONE JSON object only: start with { and end with }. "
            'Shape: {"rows": [ {"testcase": "...", "description": "...", "precondition": "...", '
            '"test_steps": "...", "expected_results": "..." }, ... ] }. '
            "No markdown fences, no text outside the JSON."
        )
        if self._poc.max_test_scenarios == 2 or self._poc.enabled:
            user_prompt += (
                "\n\nLIMIT: Match the number of scenarios in the plan (typically two rows: "
                "one positive, one negative)."
            )

        doc: TestMatrixDocument = self.llm.generate(
            system_prompt, user_prompt, TestMatrixDocument
        )
        if not doc.rows:
            doc = TestMatrixDocument(
                rows=[
                    TestMatrixRow(
                        testcase=(s[:120] if len(s) > 120 else s) or "scenario",
                        description=s,
                        precondition="Application under test is available.",
                        test_steps=(
                            "1. Execute the scenario as described in the JIRA ticket.\n"
                            "2. Observe actual behavior."
                        ),
                        expected_results="Behavior matches the ticket and acceptance criteria.",
                    )
                    for s in plan.test_scenarios
                ]
            )
        if not doc.rows:
            doc = TestMatrixDocument(
                rows=[
                    TestMatrixRow(
                        testcase=ticket.id,
                        description=ticket.title,
                        precondition="",
                        test_steps="Follow the ticket description and acceptance criteria.",
                        expected_results="All acceptance criteria satisfied.",
                    )
                ]
            )

        doc = _normalize_test_matrix_rows(doc, ticket.id)

        headers = ["testcase", "Description", "PreCondition", "TestSteps", "Expected Results"]
        abs_path = str(out_path.resolve())
        with out_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for r in doc.rows:
                writer.writerow(
                    [
                        r.testcase,
                        r.description,
                        r.precondition,
                        r.test_steps,
                        r.expected_results,
                    ]
                )

        self.console.print(f"[green]Test matrix written to {abs_path}[/green]")
        self._u(
            "SUCCESS",
            f"Test matrix saved ({len(doc.rows)} row(s)) — {abs_path}",
        )
        if self._on_matrix_csv is not None:
            self._on_matrix_csv(abs_path)

        return {"test_matrix_csv_path": abs_path, "phase": "matrix_csv_complete"}
```

## Appendix D — `docs/test_matrix.md` (full file, verbatim)

```markdown
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

```

---

*End of single-file plan.*
