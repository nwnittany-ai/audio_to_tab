"""audio2tab GUI — main window."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QSpinBox, QPushButton, QGroupBox, QSplitter,
    QMenuBar, QMessageBox, QFileDialog,
)
from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QAction, QFont

# Add project root to path so core/ and config/ are importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.tunings import ALL_TUNINGS
from core.pipeline import run as pipeline_run
from gui.cli_reference import CliReferenceDialog
from gui.widgets.file_picker import FilePicker
from gui.widgets.stage_panel import StagePanel
from gui.widgets.tab_preview import TabPreview


# ---------------------------------------------------------------------------
# Pipeline worker — runs in a background thread so the UI stays responsive
# ---------------------------------------------------------------------------

class PipelineSignals(QObject):
    log = Signal(str, str)   # (stage_name, message)
    stage_done = Signal(str, str)  # (stage_name, summary)
    finished = Signal(dict)
    error = Signal(str)


class PipelineWorker(QThread):
    def __init__(self, kwargs: dict, parent=None):
        super().__init__(parent)
        self.kwargs = kwargs
        self.signals = PipelineSignals()
        self._setup_log_handler()

    def _setup_log_handler(self):
        """Route logging output to the GUI via signals."""
        signals = self.signals

        class GuiHandler(logging.Handler):
            def emit(self, record):
                msg = record.getMessage()
                stage = "pipeline"
                for s in ("Stage 1", "Stage 2", "Stage 3", "Stage 4"):
                    if s.lower().replace(" ", "") in record.name.lower() or s in msg:
                        stage = s
                        break
                signals.log.emit(stage, msg)

        self._handler = GuiHandler()
        logging.getLogger().addHandler(self._handler)

    def run(self):
        try:
            result = pipeline_run(**self.kwargs)
            self.signals.finished.emit(result)
        except Exception as exc:
            self.signals.error.emit(str(exc))
        finally:
            logging.getLogger().removeHandler(self._handler)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("audio2tab")
        self.resize(900, 720)
        self._worker: PipelineWorker | None = None
        self._tab_path: Path | None = None

        self._build_menu()
        self._build_ui()

    # ------------------------------------------------------------------
    # Menu bar
    # ------------------------------------------------------------------

    def _build_menu(self):
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("File")
        open_act = QAction("Open Audio File…", self)
        open_act.setShortcut("Ctrl+O")
        open_act.triggered.connect(self._open_file)
        file_menu.addAction(open_act)

        save_act = QAction("Save Tab As…", self)
        save_act.setShortcut("Ctrl+S")
        save_act.triggered.connect(self._save_tab)
        file_menu.addAction(save_act)

        file_menu.addSeparator()
        quit_act = QAction("Quit", self)
        quit_act.setShortcut("Ctrl+Q")
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

        # Help menu
        help_menu = menubar.addMenu("Help")
        cli_act = QAction("CLI Reference…", self)
        cli_act.triggered.connect(self._show_cli_reference)
        help_menu.addAction(cli_act)

        about_act = QAction("About audio2tab", self)
        about_act.triggered.connect(self._show_about)
        help_menu.addAction(about_act)

    # ------------------------------------------------------------------
    # Main UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(8)

        # --- Input file ---
        input_group = QGroupBox("Input")
        ig_layout = QVBoxLayout(input_group)
        self._file_picker = FilePicker()
        self._file_picker.file_selected.connect(self._on_file_selected)
        ig_layout.addWidget(self._file_picker)
        root.addWidget(input_group)

        # --- Options ---
        opts_group = QGroupBox("Options")
        opts_layout = QHBoxLayout(opts_group)

        opts_layout.addWidget(QLabel("Tuning:"))
        self._tuning_combo = QComboBox()
        self._tuning_combo.addItems(sorted(ALL_TUNINGS.keys()))
        self._tuning_combo.setCurrentText("standard")
        self._tuning_combo.setMinimumWidth(140)
        opts_layout.addWidget(self._tuning_combo)

        opts_layout.addWidget(QLabel("Instrument:"))
        self._instrument_combo = QComboBox()
        self._instrument_combo.addItems(["auto", "guitar", "bass"])
        opts_layout.addWidget(self._instrument_combo)

        opts_layout.addWidget(QLabel("Quantize:"))
        self._quantize_combo = QComboBox()
        self._quantize_combo.addItems(["4th", "8th", "16th", "32nd"])
        self._quantize_combo.setCurrentText("8th")
        opts_layout.addWidget(self._quantize_combo)

        opts_layout.addWidget(QLabel("Measures/line:"))
        self._mpl_spin = QSpinBox()
        self._mpl_spin.setRange(1, 8)
        self._mpl_spin.setValue(4)
        opts_layout.addWidget(self._mpl_spin)

        opts_layout.addStretch()
        root.addWidget(opts_group)

        # --- Run button ---
        btn_row = QHBoxLayout()
        self._run_btn = QPushButton("Run Pipeline")
        self._run_btn.setFixedHeight(36)
        self._run_btn.setEnabled(False)
        self._run_btn.clicked.connect(self._run_pipeline)
        btn_row.addWidget(self._run_btn)

        self._save_btn = QPushButton("Save Tab As…")
        self._save_btn.setFixedHeight(36)
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._save_tab)
        btn_row.addWidget(self._save_btn)

        root.addLayout(btn_row)

        # --- Stage panels + tab preview in a splitter ---
        splitter = QSplitter(Qt.Orientation.Vertical)

        stages_widget = QWidget()
        stages_layout = QVBoxLayout(stages_widget)
        stages_layout.setContentsMargins(0, 0, 0, 0)
        stages_layout.addWidget(QLabel("<b>Pipeline stages</b>"))

        stage_row = QHBoxLayout()
        self._stage_panels = {}
        for name in ("Stage 1: Extract", "Stage 2: Process", "Stage 3: Map", "Stage 4: Render"):
            panel = StagePanel(name)
            self._stage_panels[name] = panel
            stage_row.addWidget(panel)
        stages_layout.addLayout(stage_row)
        splitter.addWidget(stages_widget)

        preview_widget = QWidget()
        pv_layout = QVBoxLayout(preview_widget)
        pv_layout.setContentsMargins(0, 0, 0, 0)
        pv_layout.addWidget(QLabel("<b>Tab Preview</b>"))
        self._tab_preview = TabPreview()
        pv_layout.addWidget(self._tab_preview)
        splitter.addWidget(preview_widget)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        root.addWidget(splitter, stretch=1)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_file_selected(self, path: Path):
        self._run_btn.setEnabled(True)
        self._tab_preview.clear_preview()
        self._save_btn.setEnabled(False)
        for panel in self._stage_panels.values():
            panel.set_waiting()

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Audio File", "", "Audio (*.wav *.mp3)")
        if path:
            p = Path(path)
            self._file_picker.set_path(p)
            self._on_file_selected(p)

    def _run_pipeline(self):
        audio_path = self._file_picker.path()
        if not audio_path or not audio_path.exists():
            QMessageBox.warning(self, "No file", "Please select a valid audio file first.")
            return

        out_dir = audio_path.parent / "tab_output"
        self._run_btn.setEnabled(False)
        self._save_btn.setEnabled(False)

        for panel in self._stage_panels.values():
            panel.set_waiting()

        kwargs = dict(
            audio_path=audio_path,
            output_dir=out_dir,
            tuning=self._tuning_combo.currentText(),
            instrument=self._instrument_combo.currentText(),
            quantize=self._quantize_combo.currentText(),
            measures_per_line=self._mpl_spin.value(),
        )

        self._worker = PipelineWorker(kwargs)
        self._worker.signals.log.connect(self._on_log)
        self._worker.signals.finished.connect(self._on_finished)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    def _on_log(self, stage: str, message: str):
        stage_map = {
            "Stage 1": "Stage 1: Extract",
            "Stage 2": "Stage 2: Process",
            "Stage 3": "Stage 3: Map",
            "Stage 4": "Stage 4: Render",
        }
        for key, panel_name in stage_map.items():
            if key in message or key in stage:
                panel = self._stage_panels[panel_name]
                panel.set_running()
                panel.append_log(message)
                return
        # Fallback: append to the currently-running stage
        for panel in self._stage_panels.values():
            panel.append_log(message)
            break

    def _on_finished(self, summary: dict):
        self._run_btn.setEnabled(True)
        tab_path = Path(summary["tab"])
        self._tab_path = tab_path

        # Mark all stages done
        stage_summaries = [
            f"{summary['notes_raw']} raw notes",
            f"{summary['notes_kept']} kept",
            f"{summary['notes_mapped']} mapped",
            f"{summary['measures']} measures",
        ]
        for (name, panel), s in zip(self._stage_panels.items(), stage_summaries):
            panel.set_done(s)

        if tab_path.exists():
            self._tab_preview.load_file(tab_path)
            self._save_btn.setEnabled(True)

        self.statusBar().showMessage(
            f"Done — {summary['measures']} measures at {summary['tempo_bpm']:.1f} BPM  |  {tab_path}"
        )

    def _on_error(self, msg: str):
        self._run_btn.setEnabled(True)
        QMessageBox.critical(self, "Pipeline error", msg)
        for panel in self._stage_panels.values():
            if "Running" in panel._status.text():
                panel.set_error(msg)

    def _save_tab(self):
        if not self._tab_path or not self._tab_path.exists():
            QMessageBox.information(self, "No tab", "Run the pipeline first to generate a tab.")
            return
        dest, _ = QFileDialog.getSaveFileName(
            self, "Save Tab As", str(self._tab_path), "Tab files (*.tab);;Text files (*.txt)"
        )
        if dest:
            Path(dest).write_text(self._tab_path.read_text(encoding="utf-8"), encoding="utf-8")
            self.statusBar().showMessage(f"Saved to {dest}")

    def _show_cli_reference(self):
        dlg = CliReferenceDialog(self)
        dlg.exec()

    def _show_about(self):
        QMessageBox.about(
            self, "About audio2tab",
            "<b>audio2tab</b> v0.1.0<br><br>"
            "Converts audio files to guitar/bass tab<br>"
            "using Basic Pitch pitch detection.<br><br>"
            "Pipeline: Extract → Process → Map → Render<br><br>"
            "See <b>Help → CLI Reference</b> for command-line usage."
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("audio2tab")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
