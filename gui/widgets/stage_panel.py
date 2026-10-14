"""Stage panel — shows per-stage status and log output."""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget


class StagePanel(QWidget):
    """Displays a status label + scrolling log for one pipeline stage."""

    WAITING, RUNNING, DONE, SKIPPED, ERROR = "waiting", "running", "done", "skipped", "error"

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.state = self.WAITING
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header = QLabel(f"<b>{title}</b>")
        layout.addWidget(header)

        self._status = QLabel("Waiting…")
        self._status.setStyleSheet("color: gray;")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(80)
        font = QFont("Courier New", 8)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._log.setFont(font)
        layout.addWidget(self._log)

    def is_running(self) -> bool:
        return self.state == self.RUNNING

    def status_text(self) -> str:
        return self._status.text()

    def set_running(self):
        self.state = self.RUNNING
        self._status.setText("Running…")
        self._status.setStyleSheet("color: #0070C0;")

    def set_done(self, summary: str = ""):
        self.state = self.DONE
        self._status.setText(f"Done. {summary}".strip())
        self._status.setStyleSheet("color: green;")

    def set_skipped(self, reason: str = ""):
        self.state = self.SKIPPED
        self._status.setText(f"Skipped. {reason}".strip())
        self._status.setStyleSheet("color: gray;")

    def set_error(self, msg: str):
        self.state = self.ERROR
        self._status.setText(f"Error: {msg}")
        self._status.setStyleSheet("color: red;")

    def set_waiting(self):
        self.state = self.WAITING
        self._status.setText("Waiting…")
        self._status.setStyleSheet("color: gray;")
        self._log.clear()

    def append_log(self, text: str):
        self._log.appendPlainText(text)
        self._log.verticalScrollBar().setValue(self._log.verticalScrollBar().maximum())
