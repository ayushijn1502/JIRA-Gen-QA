from __future__ import annotations

import sys

from PySide6.QtCore import (
    Q_ARG,
    QMetaObject,
    QObject,
    Qt,
    QThread,
    Signal,
    Slot,
)
from PySide6.QtGui import QColor, QFont, QPalette, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from main import execute_run


class RunWorker(QObject):
    log_line = Signal(str, str)
    finished = Signal(str)

    def __init__(
        self,
        ticket_id: str,
        config_path: str,
        text_input_callback,
    ) -> None:
        super().__init__()
        self.ticket_id = ticket_id
        self.config_path = config_path
        self.text_input_callback = text_input_callback

    @Slot()
    def run(self) -> None:
        try:
            phase = execute_run(
                ticket_id=self.ticket_id,
                config=self.config_path,
                user_log=lambda level, message: self.log_line.emit(level, message),
                text_input=self.text_input_callback,
            )
            self.finished.emit(phase)
        except Exception:
            self.finished.emit("failed")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._thread: QThread | None = None
        self._worker: RunWorker | None = None
        self._approval_answer = "n"
        self.setWindowTitle("AutoTest Agent")
        self.resize(1000, 760)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        header = QFrame()
        header_layout = QVBoxLayout(header)
        brand = QLabel("JIRA Gen QA")
        brand.setStyleSheet("font-size: 26px; font-weight: 700; color: #d8ddff;")
        subtitle = QLabel("JIRA -> AI -> Pytest -> GitHub")
        subtitle.setStyleSheet("color: #94a3b8;")
        header_layout.addWidget(brand)
        header_layout.addWidget(subtitle)
        outer.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setSpacing(12)

        input_card = self._card("Run configuration")
        form = QFormLayout()
        self.ticket_input = QLineEdit()
        self.ticket_input.setPlaceholderText("PROJ-123")
        self.config_input = QLineEdit("config.yaml")
        form.addRow("Ticket ID", self.ticket_input)
        form.addRow("Config path", self.config_input)
        input_card.layout().addLayout(form)
        body_layout.addWidget(input_card)

        action_card = self._card("Actions")
        row = QHBoxLayout()
        self.start_btn = QPushButton("Run pipeline")
        self.start_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.start_btn.clicked.connect(self._on_start)
        self.status_label = QLabel("Idle")
        self.status_label.setStyleSheet("color: #94a3b8;")
        row.addWidget(self.start_btn)
        row.addWidget(self.status_label)
        row.addStretch()
        action_card.layout().addLayout(row)
        body_layout.addWidget(action_card)

        log_card = self._card("Activity log")
        hint = QLabel("Shows user-friendly updates only (INFO, SUCCESS, WARN, ERROR).")
        hint.setStyleSheet("color: #94a3b8;")
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(360)
        log_card.layout().addWidget(hint)
        log_card.layout().addWidget(self.log)
        body_layout.addWidget(log_card)
        body_layout.addStretch(1)

        scroll.setWidget(body)
        outer.addWidget(scroll)
        self.setCentralWidget(root)

    def _card(self, title: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        label = QLabel(title)
        label.setStyleSheet("font-size: 15px; font-weight: 600; color: #d8ddff;")
        layout.addWidget(label)
        return frame

    @Slot()
    def _on_start(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            QMessageBox.information(self, "Run in progress", "Please wait for the current run to finish.")
            return

        ticket_id = self.ticket_input.text().strip()
        if not ticket_id:
            QMessageBox.warning(self, "Missing ticket", "Please enter a JIRA ticket ID.")
            return

        self.log.clear()
        self.start_btn.setEnabled(False)
        self.status_label.setText("Running")

        self._thread = QThread(self)
        self._worker = RunWorker(
            ticket_id=ticket_id,
            config_path=self.config_input.text().strip() or "config.yaml",
            text_input_callback=self._make_text_input(),
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.log_line.connect(self._append_log_line)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.start()

    @Slot(str)
    def _on_worker_finished(self, phase: str) -> None:
        self.status_label.setText(f"Finished: {phase}")

    @Slot()
    def _on_thread_finished(self) -> None:
        self.start_btn.setEnabled(True)
        if self._thread is not None:
            self._thread.deleteLater()
        self._thread = None
        self._worker = None

    def _make_text_input(self):
        def ask(prompt: str) -> str:
            body = prompt
            QMetaObject.invokeMethod(
                self,
                "_approval_dialog_slot",
                Qt.ConnectionType.BlockingQueuedConnection,
                Q_ARG(str, body),
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

    @Slot(str, str)
    def _append_log_line(self, level: str, message: str) -> None:
        cursor = self.log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        level_color = {
            "INFO": "#93c5fd",
            "SUCCESS": "#86efac",
            "WARN": "#fcd34d",
            "ERROR": "#fda4af",
        }.get(level, "#cbd5e1")
        fmt.setForeground(QColor(level_color))
        cursor.insertText(f"{level}: ", fmt)
        plain_fmt = QTextCharFormat()
        plain_fmt.setForeground(QColor("#e2e8f0"))
        cursor.insertText(f"{message}\n", plain_fmt)
        self.log.setTextCursor(cursor)
        self.log.ensureCursorVisible()

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
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#1f2937"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#e2e8f0"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#1e293b"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#e2e8f0"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#4f46e5"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)
    app.setStyleSheet(
        """
        QFrame#card { background: #111827; border: 1px solid #1f2937; border-radius: 12px; }
        QLineEdit, QTextEdit { background: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 8px; color: #e2e8f0; }
        QLineEdit:focus, QTextEdit:focus { border: 1px solid #6366f1; }
        QPushButton { background: #4f46e5; color: white; border: none; border-radius: 18px; padding: 8px 16px; font-weight: 600; }
        QPushButton:disabled { background: #334155; color: #94a3b8; }
        QScrollBar:vertical { background: #0b1020; width: 10px; margin: 0; }
        QScrollBar::handle:vertical { background: #334155; min-height: 30px; border-radius: 5px; }
        """
    )


def main() -> None:
    app = QApplication(sys.argv)
    _apply_theme(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
