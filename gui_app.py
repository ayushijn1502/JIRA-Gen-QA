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
                config="config.yaml",
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
