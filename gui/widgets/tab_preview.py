"""Tab preview pane — monospace scrollable view of rendered ASCII tab."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QPlainTextEdit, QSizePolicy
from PySide6.QtGui import QFont


class TabPreview(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont("Courier New", 9)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setPlaceholderText("Tab output will appear here after rendering…")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def load_file(self, path: Path):
        try:
            self.setPlainText(path.read_text(encoding="utf-8"))
            self.verticalScrollBar().setValue(0)
        except Exception as exc:
            self.setPlainText(f"Could not load tab file:\n{exc}")

    def clear_preview(self):
        self.clear()
