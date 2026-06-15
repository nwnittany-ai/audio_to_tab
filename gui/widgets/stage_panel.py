"""Stage panel — shows per-stage status and log output."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


class StagePanel(QWidget):
    """Displays a status label + scrolling log for one pipeline stage."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header = QLabel(f"<b>{title}</b>")
        layout.addWidget(header)

        self._status = QLabel("Waiting…")
        self._status.setStyleSheet("color: gray;")
        layout.addWidget(self._status)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(80)
        font = QFont("Courier New", 8)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._log.setFont(font)
        layout.addWidget(self._log)

    def set_running(self):
        self._status.setText("Running…")
        self._status.setStyleSheet("color: #0070C0;")

    def set_done(self, summary: str = ""):
        self._status.setText(f"Done. {summary}")
        self._status.setStyleSheet("color: green;")

    def set_error(self, msg: str):
        self._status.setText(f"Error: {msg}")
        self._status.setStyleSheet("color: red;")

    def set_waiting(self):
        self._status.setText("Waiting…")
        self._status.setStyleSheet("color: gray;")
        self._log.clear()

    def append_log(self, text: str):
        self._log.appendPlainText(text)
        self._log.verticalScrollBar().setValue(self._log.verticalScrollBar().maximum())
