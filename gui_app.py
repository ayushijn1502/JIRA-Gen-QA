from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import Q_ARG, QMetaObject, QObject, Qt, QThread, Signal, Slot
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from main import execute_run

PIPELINE_STEPS = [
    ("started", "Getting ready", "Pipeline bootstrapping."),
    ("settings", "Settings loaded", "Configuration and services are loaded."),
    ("gemini_check", "Checking AI connection", "Gemini API/model connection check."),
    ("indexing", "Scanning project code", "Reading target framework code for RAG."),
    ("jira_fetch", "Loading JIRA ticket", "JIRA details loaded."),
    ("analyze", "Understanding JIRA", "Analyze ticket requirements."),
    ("matrix_csv", "Building test matrix", "Test matrix CSV generated."),
    ("generate", "Creating automation", "Generate test code."),
    ("verify", "Running tests", "Run pytest verification."),
    ("deploy", "Publishing / approval", "Approval and optional PR steps."),
    ("done", "Complete", "Pipeline completed."),
]
STEP_INDEX = {stage_id: idx for idx, (stage_id, _, _) in enumerate(PIPELINE_STEPS)}


def _ensure_qt_platform_plugins() -> None:
    for name in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"):
        if os.environ.get(name, "").strip() == "":
            os.environ.pop(name, None)
    try:
        import PySide6  # pylint: disable=import-outside-toplevel
    except Exception:
        return
    plugin_root = Path(PySide6.__file__).resolve().parent / "Qt" / "plugins"
    if (plugin_root / "platforms").is_dir():
        os.environ["QT_PLUGIN_PATH"] = str(plugin_root)


class RunWorker(QObject):
    pipeline_stage = Signal(str)
    status_message = Signal(str, str)
    csv_ready = Signal(str)
    finished = Signal(str)

    def __init__(self, ticket_id: str, text_input_callback) -> None:
        super().__init__()
        self.ticket_id = ticket_id
        self.text_input_callback = text_input_callback

    @Slot()
    def run(self) -> None:
        try:
            phase = execute_run(
                ticket_id=self.ticket_id,
                config="config.yaml",
                user_log=lambda level, msg: self.status_message.emit(level, msg),
                text_input=self.text_input_callback,
                on_stage=lambda stage: self.pipeline_stage.emit(stage),
                on_matrix_csv=lambda path: self.csv_ready.emit(path),
            )
            self.finished.emit(phase)
        except Exception:
            self.pipeline_stage.emit("error")
            self.finished.emit("failed")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._thread: QThread | None = None
        self._worker: RunWorker | None = None
        self._approval_answer = "n"
        self._matrix_csv_path: str | None = None
        self._last_pipeline_stage = -1
        self._last_pipeline_error = ""
        self.setWindowTitle("AutoTest Agent")
        self.resize(980, 760)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        brand = QLabel("JIRA -> Matrix CSV -> Automation -> GitHub")
        brand.setStyleSheet("font-size: 20px; font-weight: 700; color: #d8ddff;")
        outer.addWidget(brand)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setSpacing(12)

        ticket_card = self._card("JIRA ticket")
        form = QFormLayout()
        self.ticket_input = QLineEdit()
        self.ticket_input.setPlaceholderText("PROJ-123")
        form.addRow("Ticket ID", self.ticket_input)
        ticket_card.layout().addLayout(form)

        status_row = QHBoxLayout()
        self.status_label = QLabel("Idle")
        self.status_label.setObjectName("status")
        self.csv_btn = QPushButton("Download CSV")
        self.csv_btn.setEnabled(False)
        self.csv_btn.clicked.connect(self._download_csv)
        self.start_btn = QPushButton("Run pipeline")
        self.start_btn.clicked.connect(self._on_start)
        status_row.addWidget(self.status_label, 1)
        status_row.addWidget(self.csv_btn)
        status_row.addWidget(self.start_btn)
        ticket_card.layout().addLayout(status_row)
        body_layout.addWidget(ticket_card)

        progress_card = self._card("Pipeline progress")
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, len(PIPELINE_STEPS))
        progress_card.layout().addWidget(self.progress_bar)
        self.hint_label = QLabel("Run the pipeline to see progress stages.")
        self.hint_label.setStyleSheet("color: #94a3b8;")
        progress_card.layout().addWidget(self.hint_label)

        timeline_host = QWidget()
        self.timeline_layout = QHBoxLayout(timeline_host)
        self.timeline_layout.setSpacing(10)
        self.timeline_rows: list[tuple[QLabel, QLabel]] = []
        for idx, (_, title, desc) in enumerate(PIPELINE_STEPS):
            row = QWidget()
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            badge = QLabel("○")
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title_lbl = QLabel(title)
            title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title_lbl.setWordWrap(True)
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet("color: #94a3b8;")
            desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            desc_lbl.setWordWrap(True)
            row_layout.addWidget(badge)
            row_layout.addWidget(title_lbl)
            row_layout.addWidget(desc_lbl)
            self.timeline_layout.addWidget(row)
            if idx < len(PIPELINE_STEPS) - 1:
                connector = QLabel("—")
                connector.setStyleSheet("color: #475569;")
                self.timeline_layout.addWidget(connector)
            self.timeline_rows.append((badge, title_lbl))
        progress_card.layout().addWidget(timeline_host)
        body_layout.addWidget(progress_card)
        body_layout.addStretch(1)

        scroll.setWidget(body)
        outer.addWidget(scroll)
        self.setCentralWidget(root)
        self._reset_pipeline_visual()

    def _card(self, title: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        label = QLabel(title)
        label.setStyleSheet("font-size: 15px; font-weight: 600; color: #d8ddff;")
        layout.addWidget(label)
        return frame

    def _reset_pipeline_visual(self) -> None:
        self._last_pipeline_stage = -1
        self._last_pipeline_error = ""
        self.progress_bar.setValue(0)
        self.hint_label.setVisible(True)
        for badge, title in self.timeline_rows:
            badge.setText("○")
            badge.setStyleSheet("color: #64748b;")
            title.setStyleSheet("color: #64748b;")
            badge.setToolTip("")
            title.setToolTip("")
            badge.parentWidget().setVisible(False)

    @Slot(str)
    def _apply_pipeline_stage(self, stage_id: str) -> None:
        idx = STEP_INDEX.get(stage_id, self._last_pipeline_stage)
        self._last_pipeline_stage = max(self._last_pipeline_stage, idx)
        self.progress_bar.setValue(max(0, self._last_pipeline_stage + 1))
        self.hint_label.setVisible(False)
        for i, (badge, title) in enumerate(self.timeline_rows):
            badge.parentWidget().setVisible(True)
            if stage_id == "error" and i == self._last_pipeline_stage:
                badge.setText("✕")
                badge.setStyleSheet("color: #f87171;")
                title.setStyleSheet("color: #fca5a5;")
                if self._last_pipeline_error:
                    badge.setToolTip(self._last_pipeline_error)
                    title.setToolTip(self._last_pipeline_error)
            elif i < self._last_pipeline_stage:
                badge.setText("●")
                badge.setStyleSheet("color: #34d399;")
                title.setStyleSheet("color: #cbd5e1;")
            elif i == self._last_pipeline_stage:
                badge.setText("◉")
                badge.setStyleSheet("color: #818cf8;")
                title.setStyleSheet("color: #e2e8f0;")
            else:
                badge.setText("○")
                badge.setStyleSheet("color: #64748b;")
                title.setStyleSheet("color: #64748b;")

    @Slot()
    def _on_start(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            QMessageBox.information(self, "Run in progress", "Please wait for the current run to finish.")
            return
        ticket_id = self.ticket_input.text().strip()
        if not ticket_id:
            QMessageBox.warning(self, "Missing ticket", "Please enter a JIRA ticket ID.")
            return
        self._reset_pipeline_visual()
        self._matrix_csv_path = None
        self.csv_btn.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.status_label.setText("INFO: Running pipeline.")

        self._thread = QThread(self)
        self._worker = RunWorker(ticket_id=ticket_id, text_input_callback=self._make_text_input())
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.status_message.connect(self._on_status_message)
        self._worker.pipeline_stage.connect(self._apply_pipeline_stage)
        self._worker.csv_ready.connect(self._on_csv_ready)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.start()

    @Slot(str, str)
    def _on_status_message(self, level: str, message: str) -> None:
        self.status_label.setText(f"{level}: {message}")
        if level.upper() == "ERROR":
            self._last_pipeline_error = message

    @Slot(str)
    def _on_csv_ready(self, path: str) -> None:
        self._matrix_csv_path = path
        self.csv_btn.setEnabled(Path(path).exists())

    @Slot(str)
    def _on_worker_finished(self, phase: str) -> None:
        if phase == "failed":
            self.status_label.setText("ERROR: Pipeline failed.")

    @Slot()
    def _on_thread_finished(self) -> None:
        self.start_btn.setEnabled(True)
        if self._thread is not None:
            self._thread.deleteLater()
        self._thread = None
        self._worker = None

    def _make_text_input(self):
        def ask(prompt: str) -> str:
            QMetaObject.invokeMethod(
                self,
                "_approval_dialog_slot",
                Qt.ConnectionType.BlockingQueuedConnection,
                Q_ARG(str, prompt),
            )
            return self._approval_answer

        return ask

    @Slot(str)
    def _approval_dialog_slot(self, body: str) -> None:
        reply = QMessageBox.question(
            self,
            "Approval required",
            body,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        self._approval_answer = "y" if reply == QMessageBox.StandardButton.Yes else "n"

    @Slot()
    def _download_csv(self) -> None:
        if not self._matrix_csv_path or not Path(self._matrix_csv_path).exists():
            QMessageBox.warning(self, "CSV unavailable", "No matrix CSV has been generated yet.")
            return
        dest, _ = QFileDialog.getSaveFileName(
            self,
            "Save test matrix CSV",
            Path(self._matrix_csv_path).name,
            "CSV Files (*.csv)",
        )
        if not dest:
            return
        shutil.copyfile(self._matrix_csv_path, dest)
        QMessageBox.information(self, "Saved", f"CSV saved to:\n{dest}")

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._thread is not None and self._thread.isRunning():
            QMessageBox.information(
                self,
                "Run in progress",
                "Please wait for the current run to finish before closing the window.",
            )
            event.ignore()
            return
        super().closeEvent(event)


def _apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#0b1020"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#e2e8f0"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#111827"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#e2e8f0"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#1e293b"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#e2e8f0"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#4f46e5"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)
    app.setStyleSheet(
        """
        QFrame#card { background: #111827; border: 1px solid #1f2937; border-radius: 12px; }
        QLineEdit { background: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 8px; color: #e2e8f0; }
        QLineEdit:focus { border: 1px solid #6366f1; }
        QPushButton { background: #4f46e5; color: white; border: none; border-radius: 16px; padding: 8px 16px; font-weight: 600; }
        QPushButton:disabled { background: #334155; color: #94a3b8; }
        QLabel#status { color: #93c5fd; }
        QProgressBar { border: 1px solid #334155; border-radius: 4px; background: #0f172a; max-height: 8px; }
        QProgressBar::chunk { background: #6366f1; border-radius: 4px; }
        """
    )


def main() -> None:
    _ensure_qt_platform_plugins()
    app = QApplication(sys.argv)
    _apply_theme(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
