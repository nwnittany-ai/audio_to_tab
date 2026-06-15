"""File picker widget — browse button + path display."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QPushButton, QFileDialog
from PySide6.QtCore import Signal


class FilePicker(QWidget):
    file_selected = Signal(Path)

    def __init__(self, label: str = "Browse…", filter: str = "Audio (*.wav *.mp3)", parent=None):
        super().__init__(parent)
        self._filter = filter

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("No file selected")
        self._path_edit.setReadOnly(True)
        layout.addWidget(self._path_edit, stretch=1)

        btn = QPushButton(label)
        btn.setFixedWidth(90)
        btn.clicked.connect(self._browse)
        layout.addWidget(btn)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select audio file", "", self._filter)
        if path:
            p = Path(path)
            self._path_edit.setText(str(p))
            self.file_selected.emit(p)

    def path(self) -> Path | None:
        t = self._path_edit.text().strip()
        return Path(t) if t else None

    def set_path(self, p: Path):
        self._path_edit.setText(str(p))
