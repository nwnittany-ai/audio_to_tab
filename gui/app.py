"""audio2tab GUI -- main window.

Laid out like the stem maker: Main / Advanced / CLI Reference tabs, a chosen output folder with an
"Open Output Folder" button, settings you can keep (Save Settings), and a warning before overwriting files.
All processing lives in core/ -- this window only wraps core.pipeline.run (the same function the CLI calls),
handles layout and threading, and never makes its own decisions about the music.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path


def ensure_streams() -> None:
    """Under pythonw (the no-console launcher) sys.stdout/stderr are None, and libraries that print or draw progress
    bars would crash. Give them UTF-8 stand-ins (the default Windows encoding cannot hold progress-bar block
    characters; that exact problem crashed the stem maker's model download once)."""
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8", errors="replace"))


ensure_streams()

# Make core/ and config/ importable when started as `python gui/app.py`
sys.path.insert(0, str(Path(__file__).parent.parent))

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal  # noqa: E402
from PySide6.QtGui import QAction, QDesktopServices  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton, QSpinBox, QSplitter, QTabWidget, QVBoxLayout,
    QWidget,
)

from config import settings as app_settings  # noqa: E402
from config.defaults import INSTRUMENT_CHOICES, MIDI_TIMING_CHOICES, QUANTIZE_CHOICES, VERSION  # noqa: E402
from config.tunings import ALL_TUNINGS  # noqa: E402
from core.pipeline import STAGES  # noqa: E402
from core.pipeline import run as pipeline_run  # noqa: E402
from gui.cli_reference import CliReferenceView  # noqa: E402
from gui.widgets.file_picker import FilePicker  # noqa: E402
from gui.widgets.stage_panel import StagePanel  # noqa: E402
from gui.widgets.tab_preview import TabPreview  # noqa: E402

APP_TITLE = "audio2tab"
MIDI_TIMING_LABELS = {"played": "As played (keeps the feel)", "grid": "Snapped to the grid"}


# ---------------------------------------------------------------------------
# Pipeline worker -- runs in a background thread so the window stays responsive
# ---------------------------------------------------------------------------

class PipelineSignals(QObject):
    log = Signal(str)               # one log line
    stage = Signal(str, str, str)   # (stage name, running|done|skipped, summary)
    finished = Signal(dict)
    error = Signal(str)


class _GuiLogHandler(logging.Handler):
    def __init__(self, signal):
        super().__init__()
        self._signal = signal

    def emit(self, record):
        self._signal.emit(record.getMessage())


class PipelineWorker(QThread):
    def __init__(self, pipeline, kwargs: dict, parent=None):
        super().__init__(parent)
        self._pipeline = pipeline
        self._kwargs = kwargs
        self.signals = PipelineSignals()

    def run(self):
        handler = _GuiLogHandler(self.signals.log)
        root = logging.getLogger()
        root.addHandler(handler)
        try:
            result = self._pipeline(progress=self.signals.stage.emit, **self._kwargs)
            self.signals.finished.emit(result)
        except Exception as exc:
            self.signals.error.emit(str(exc))
        finally:
            root.removeHandler(handler)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self, settings_path: Path | None = None, pipeline=None):
        super().__init__()
        self._settings_path = settings_path
        self._pipeline = pipeline or pipeline_run
        self._cfg = app_settings.load(settings_path)
        self._worker: PipelineWorker | None = None
        self._tab_path: Path | None = None
        self._last_output_dir: Path | None = None
        self._output_override: Path | None = None
        self._current_stage: str | None = None

        self.setWindowTitle(f"{APP_TITLE} v{VERSION}")
        self.resize(980, 820)
        self._build_menu()
        self._build_tabs()
        self._apply(self._cfg)
        self._update_output_label()

    # ------------------------------------------------------------------ menu

    def _build_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        for text, shortcut, slot in (("Open Audio File...", "Ctrl+O", self._open_file),
                                     ("Save Tab As...", "Ctrl+S", self._save_tab),
                                     ("Open Output Folder", "Ctrl+Shift+O", self._open_output_folder)):
            act = QAction(text, self)
            act.setShortcut(shortcut)
            act.triggered.connect(slot)
            file_menu.addAction(act)
        file_menu.addSeparator()
        quit_act = QAction("Quit", self)
        quit_act.setShortcut("Ctrl+Q")
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

        help_menu = menubar.addMenu("Help")
        about_act = QAction(f"About {APP_TITLE}", self)
        about_act.triggered.connect(self._show_about)
        help_menu.addAction(about_act)

    # ------------------------------------------------------------------ tabs

    def _build_tabs(self):
        tabs = QTabWidget()
        self._tabs = tabs
        self.setCentralWidget(tabs)
        self._main_page, self._adv_page = QWidget(), QWidget()
        tabs.addTab(self._main_page, "  Main  ")
        tabs.addTab(self._adv_page, "  Advanced  ")
        tabs.addTab(CliReferenceView(), "  CLI Reference  ")
        self._build_main_tab()
        self._build_advanced_tab()

    def _build_main_tab(self):
        root = QVBoxLayout(self._main_page)
        root.setSpacing(8)

        input_group = QGroupBox("Input File")
        ig = QVBoxLayout(input_group)
        self._file_picker = FilePicker()
        self._file_picker.file_selected.connect(self._on_file_selected)
        ig.addWidget(self._file_picker)
        root.addWidget(input_group)

        out_group = QGroupBox("Output Location")
        og = QHBoxLayout(out_group)
        self._out_edit = QLineEdit()
        self._out_edit.setReadOnly(True)
        og.addWidget(self._out_edit, stretch=1)
        choose = QPushButton("Choose…")
        choose.clicked.connect(self._choose_output_dir)
        og.addWidget(choose)
        self._choose_btn = choose
        root.addWidget(out_group)

        opts_group = QGroupBox("Options  (more under the Advanced tab)")
        og2 = QHBoxLayout(opts_group)
        self._tuning_combo = QComboBox()
        self._tuning_combo.addItems(sorted(ALL_TUNINGS.keys()))
        self._tuning_combo.setMinimumWidth(140)
        self._instrument_combo = QComboBox()
        self._instrument_combo.addItems(list(INSTRUMENT_CHOICES))
        self._instrument_combo.setToolTip("auto decides guitar vs bass from the notes themselves.")
        self._quantize_combo = QComboBox()
        self._quantize_combo.addItems(list(QUANTIZE_CHOICES))
        self._mpl_spin = QSpinBox()
        self._mpl_spin.setRange(1, 8)
        self._max_fret_spin = QSpinBox()
        self._max_fret_spin.setRange(1, 24)
        self._max_fret_spin.setToolTip(
            "Highest fret allowed in the tab. Notes that can only be played above it are dropped.\n"
            "12 = first position; raise to 24 for high-fret leads."
        )
        for label, widget in (("Tuning:", self._tuning_combo), ("Instrument:", self._instrument_combo),
                              ("Quantize:", self._quantize_combo), ("Measures/line:", self._mpl_spin),
                              ("Max fret:", self._max_fret_spin)):
            og2.addWidget(QLabel(label))
            og2.addWidget(widget)
        self._chord_chk = QCheckBox("Chord symbols")
        self._chord_chk.setToolTip("Print the root note (lowest pitch) above the tab at each chord change.")
        self._midi_chk = QCheckBox("Also save MIDI (.mid)")
        self._midi_chk.setToolTip("Write the cleaned notes as a MIDI file next to the tab.")
        og2.addWidget(self._chord_chk)
        og2.addWidget(self._midi_chk)
        og2.addStretch()
        root.addWidget(opts_group)

        btn_row = QHBoxLayout()
        self._run_btn = QPushButton("Run Pipeline")
        self._run_btn.setFixedHeight(36)
        self._run_btn.setEnabled(False)
        self._run_btn.clicked.connect(self._run_pipeline)
        self._save_btn = QPushButton("Save Tab As…")
        self._save_btn.setFixedHeight(36)
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._save_tab)
        self._open_btn = QPushButton("Open Output Folder")
        self._open_btn.setFixedHeight(36)
        self._open_btn.setEnabled(False)
        self._open_btn.clicked.connect(self._open_output_folder)
        for b in (self._run_btn, self._save_btn, self._open_btn):
            btn_row.addWidget(b)
        root.addLayout(btn_row)

        self._progress = QProgressBar()
        self._progress.setRange(0, 1)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(10)
        root.addWidget(self._progress)

        splitter = QSplitter(Qt.Orientation.Vertical)
        stages_widget = QWidget()
        sl = QVBoxLayout(stages_widget)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.addWidget(QLabel("<b>Pipeline stages</b>"))
        row = QHBoxLayout()
        self._stage_panels: dict[str, StagePanel] = {}
        for name in STAGES:
            panel = StagePanel(name)
            self._stage_panels[name] = panel
            row.addWidget(panel)
        sl.addLayout(row)
        splitter.addWidget(stages_widget)

        preview_widget = QWidget()
        pl = QVBoxLayout(preview_widget)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.addWidget(QLabel("<b>Tab Preview</b>"))
        self._tab_preview = TabPreview()
        pl.addWidget(self._tab_preview)
        splitter.addWidget(preview_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        root.addWidget(splitter, stretch=1)

    def _build_advanced_tab(self):
        grid = QGridLayout(self._adv_page)
        grid.setColumnStretch(1, 1)
        row = 0

        def label(text, r):
            grid.addWidget(QLabel(text), r, 0, alignment=Qt.AlignmentFlag.AlignRight)

        label("Minimum amplitude:", row)
        self._min_amp_spin = QDoubleSpinBox()
        self._min_amp_spin.setRange(0.05, 0.95)
        self._min_amp_spin.setSingleStep(0.05)
        self._min_amp_spin.setDecimals(2)
        self._min_amp_spin.setToolTip("Drop notes below this confidence (0-1). Higher = fewer notes, less noise.\n"
                                      "0.25 suits single-instrument stems; lower it if real notes are being dropped.")
        grid.addWidget(self._min_amp_spin, row, 1, alignment=Qt.AlignmentFlag.AlignLeft)
        row += 1

        label("Harmonic filter:", row)
        hbox = QHBoxLayout()
        self._harmonic_chk = QCheckBox("Suppress guitar overtones")
        self._harmonic_ratio_spin = QDoubleSpinBox()
        self._harmonic_ratio_spin.setRange(0.1, 1.0)
        self._harmonic_ratio_spin.setSingleStep(0.1)
        self._harmonic_ratio_spin.setDecimals(1)
        self._harmonic_ratio_spin.setToolTip(
            "A note a harmonic interval (octave, 5th, ...) above a louder note is dropped when it is quieter than\n"
            "this fraction of the louder note. 0.5 = drop if twice as quiet; 0.8 = more aggressive."
        )
        hbox.addWidget(self._harmonic_chk)
        hbox.addWidget(QLabel("strength:"))
        hbox.addWidget(self._harmonic_ratio_spin)
        hbox.addStretch()
        grid.addLayout(hbox, row, 1)
        row += 1

        self._filter_hint = QLabel()
        self._filter_hint.setStyleSheet("color: #666; font-style: italic;")
        self._filter_hint.setWordWrap(True)
        grid.addWidget(self._filter_hint, row, 1)
        self._min_amp_spin.valueChanged.connect(self._update_filter_hint)
        self._harmonic_ratio_spin.valueChanged.connect(self._update_filter_hint)
        self._harmonic_chk.toggled.connect(self._update_filter_hint)
        row += 1

        label("Release ghosts:", row)
        self._ghost_chk = QCheckBox("Drop short 'release ghost' notes")
        self._ghost_chk.setToolTip(
            "Lifting a finger lets the string below ring briefly; the detector reports it as a tiny extra note\n"
            "right after a note ends. Turn this on to remove those blips. Leave off if you play pull-offs or fast\n"
            "descending lines: those make real notes that look the same."
        )
        grid.addWidget(self._ghost_chk, row, 1)
        row += 1

        label("MIDI timing:", row)
        self._midi_timing_combo = QComboBox()
        for key in MIDI_TIMING_CHOICES:
            self._midi_timing_combo.addItem(MIDI_TIMING_LABELS[key], key)
        self._midi_timing_combo.setToolTip("As played keeps your performance's feel; the tab itself is always gridded.")
        grid.addWidget(self._midi_timing_combo, row, 1, alignment=Qt.AlignmentFlag.AlignLeft)
        row += 1

        label("Default input folder:", row)
        self._def_in_edit = QLineEdit()
        grid.addWidget(self._def_in_edit, row, 1)
        b = QPushButton("…")
        b.setFixedWidth(30)
        b.clicked.connect(lambda: self._browse_dir(self._def_in_edit))
        grid.addWidget(b, row, 2)
        row += 1

        label("Default output folder:", row)
        self._def_out_edit = QLineEdit()
        self._def_out_edit.setPlaceholderText("empty = a 'tab_output' folder beside each audio file")
        grid.addWidget(self._def_out_edit, row, 1)
        b = QPushButton("…")
        b.setFixedWidth(30)
        b.clicked.connect(lambda: self._browse_dir(self._def_out_edit))
        grid.addWidget(b, row, 2)
        row += 1

        btns = QHBoxLayout()
        save = QPushButton("Save Settings")
        save.clicked.connect(self._save_settings)
        reset = QPushButton("Reset to Defaults")
        reset.clicked.connect(self._reset_settings)
        btns.addStretch()
        btns.addWidget(save)
        btns.addWidget(reset)
        btns.addStretch()
        grid.addLayout(btns, row, 0, 1, 3)
        grid.setRowStretch(row + 1, 1)

    # ------------------------------------------------------------------ settings <-> widgets

    def _values(self) -> dict:
        return {
            "tuning": self._tuning_combo.currentText(),
            "instrument": self._instrument_combo.currentText(),
            "quantize": self._quantize_combo.currentText(),
            "measures_per_line": self._mpl_spin.value(),
            "max_fret": self._max_fret_spin.value(),
            "chord_symbols": self._chord_chk.isChecked(),
            "midi": self._midi_chk.isChecked(),
            "midi_timing": self._midi_timing_combo.currentData(),
            "min_amplitude": round(self._min_amp_spin.value(), 2),
            "suppress_harmonics": self._harmonic_chk.isChecked(),
            "harmonic_ratio": round(self._harmonic_ratio_spin.value(), 1),
            "ghost_filter": self._ghost_chk.isChecked(),
            "default_input_dir": self._def_in_edit.text().strip(),
            "default_output_dir": self._def_out_edit.text().strip(),
        }

    def _apply(self, v: dict):
        self._tuning_combo.setCurrentText(v["tuning"])
        self._instrument_combo.setCurrentText(v["instrument"])
        self._quantize_combo.setCurrentText(v["quantize"])
        self._mpl_spin.setValue(v["measures_per_line"])
        self._max_fret_spin.setValue(v["max_fret"])
        self._chord_chk.setChecked(v["chord_symbols"])
        self._midi_chk.setChecked(v["midi"])
        self._midi_timing_combo.setCurrentIndex(max(0, self._midi_timing_combo.findData(v["midi_timing"])))
        self._min_amp_spin.setValue(v["min_amplitude"])
        self._harmonic_chk.setChecked(v["suppress_harmonics"])
        self._harmonic_ratio_spin.setValue(v["harmonic_ratio"])
        self._ghost_chk.setChecked(v["ghost_filter"])
        self._def_in_edit.setText(v["default_input_dir"])
        self._def_out_edit.setText(v["default_output_dir"])
        self._file_picker.start_dir = v["default_input_dir"]
        self._update_filter_hint()
        self._update_output_label()

    def _save_settings(self):
        values = self._values()
        try:
            app_settings.save(values, self._settings_path)
        except OSError as exc:
            QMessageBox.critical(self, "Settings", f"Could not save settings:\n{exc}")
            return
        self._file_picker.start_dir = values["default_input_dir"]
        self._update_output_label()
        QMessageBox.information(self, "Settings", "Settings saved.")

    def _reset_settings(self):
        self._apply(app_settings.factory())
        self.statusBar().showMessage("Defaults restored in the window (click Save Settings to keep them).")

    def _update_filter_hint(self):
        amp, ratio = self._min_amp_spin.value(), self._harmonic_ratio_spin.value()
        if not self._harmonic_chk.isChecked():
            text = (f"Amplitude {amp:.2f}; overtone suppression is off - best for mixed recordings where real notes "
                    "sit at octaves and fifths.")
        elif amp >= 0.35 and ratio >= 0.7:
            text = f"Amplitude {amp:.2f}, harmonic {ratio:.1f} - very aggressive: maximum noise rejection, may drop quiet real notes."
        elif amp >= 0.25 and ratio >= 0.5:
            text = f"Amplitude {amp:.2f}, harmonic {ratio:.1f} - moderate filtering: recommended for clean single-instrument stems."
        elif amp >= 0.20 and ratio >= 0.4:
            text = f"Amplitude {amp:.2f}, harmonic {ratio:.1f} - light filtering: good for stems with some background noise."
        else:
            text = f"Amplitude {amp:.2f}, harmonic {ratio:.1f} - minimal filtering: captures most notes; expect some false positives."
        self._filter_hint.setText(text)

    # ------------------------------------------------------------------ files and folders

    def _output_dir_for(self, audio_path: Path) -> Path:
        if self._output_override:
            return self._output_override
        default = self._def_out_edit.text().strip()
        return Path(default) if default else audio_path.parent / "tab_output"

    def _update_output_label(self):
        audio = self._file_picker.path()
        if audio:
            self._out_edit.setText(str(self._output_dir_for(audio)))
        else:
            default = self._def_out_edit.text().strip()
            self._out_edit.setText(default or "A 'tab_output' folder beside the audio file")

    def _browse_dir(self, edit: QLineEdit):
        path = QFileDialog.getExistingDirectory(self, "Select folder", edit.text() or str(Path.home()))
        if path:
            edit.setText(path)

    def _choose_output_dir(self):
        audio = self._file_picker.path()
        start = str(self._output_dir_for(audio)) if audio else (self._def_out_edit.text() or str(Path.home()))
        path = QFileDialog.getExistingDirectory(self, "Select output folder", start)
        if path:
            self._output_override = Path(path)
            self._update_output_label()

    def _on_file_selected(self, path: Path):
        self._output_override = None
        self._run_btn.setEnabled(True)
        self._save_btn.setEnabled(False)
        self._open_btn.setEnabled(False)
        self._tab_preview.clear_preview()
        for panel in self._stage_panels.values():
            panel.set_waiting()
        self._update_output_label()
        self.statusBar().showMessage("Ready.")

    def _open_file(self):
        start = self._def_in_edit.text().strip() or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "Open Audio File", start, "Audio (*.wav *.mp3)")
        if path:
            p = Path(path)
            self._file_picker.set_path(p)
            self._on_file_selected(p)

    @staticmethod
    def _expected_outputs(audio: Path, out_dir: Path, midi: bool) -> list[Path]:
        stem = audio.stem
        files = [out_dir / f"{stem}.tab", out_dir / f"{stem}_notes.json", out_dir / f"{stem}_processed.json",
                 out_dir / f"{stem}_mapped.json"]
        if midi:
            files.append(out_dir / f"{stem}.mid")
        return files

    def _reveal(self, path: Path):
        """Show a file (or folder) in Explorer."""
        try:
            if sys.platform == "win32" and path.is_file():
                subprocess.Popen(["explorer", "/select,", str(path)])
            elif sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path if path.is_dir() else path.parent)))
        except OSError as exc:
            QMessageBox.warning(self, "Open folder", f"Could not open the folder:\n{exc}")

    def _open_output_folder(self):
        if self._tab_path and self._tab_path.exists():
            self._reveal(self._tab_path)
        elif self._last_output_dir and self._last_output_dir.exists():
            self._reveal(self._last_output_dir)

    # ------------------------------------------------------------------ running

    def _set_busy(self, busy: bool):
        self._run_btn.setEnabled(not busy)
        self._choose_btn.setEnabled(not busy)
        self._progress.setRange(0, 0 if busy else 1)

    def _run_pipeline(self):
        audio = self._file_picker.path()
        if not audio or not audio.exists():
            QMessageBox.warning(self, "No file", "Please select a valid audio file first.")
            return
        values = self._values()
        out_dir = self._output_dir_for(audio)
        existing = [p for p in self._expected_outputs(audio, out_dir, values["midi"]) if p.exists()]
        if existing:
            names = "\n".join(p.name for p in existing)
            answer = QMessageBox.question(
                self, "Overwrite?", f"These files already exist in\n{out_dir}\n\n{names}\n\nOverwrite them?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return

        self._set_busy(True)
        self._save_btn.setEnabled(False)
        self._open_btn.setEnabled(False)
        self._current_stage = None
        for panel in self._stage_panels.values():
            panel.set_waiting()
        self.statusBar().showMessage("Running…")

        kwargs = dict(
            audio_path=audio, output_dir=out_dir,
            tuning=values["tuning"], instrument=values["instrument"], quantize=values["quantize"],
            measures_per_line=values["measures_per_line"], max_fret=values["max_fret"],
            chord_symbols=values["chord_symbols"], midi=values["midi"], midi_timing=values["midi_timing"],
            min_amplitude=values["min_amplitude"], suppress_harmonics=values["suppress_harmonics"],
            harmonic_ratio=values["harmonic_ratio"], ghost_filter=values["ghost_filter"],
        )
        self._worker = PipelineWorker(self._pipeline, kwargs)
        self._worker.signals.stage.connect(self._on_stage)
        self._worker.signals.log.connect(self._on_log)
        self._worker.signals.finished.connect(self._on_finished)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()

    def _on_stage(self, stage: str, state: str, text: str):
        panel = self._stage_panels.get(stage)
        if panel is None:
            return
        if state == "running":
            self._current_stage = stage
            panel.set_running()
        elif state == "done":
            panel.set_done(text)
        elif state == "skipped":
            panel.set_skipped(text)

    def _on_log(self, message: str):
        panel = self._stage_panels.get(self._current_stage) if self._current_stage else None
        (panel or next(iter(self._stage_panels.values()))).append_log(message)

    def _on_finished(self, summary: dict):
        self._set_busy(False)
        self._tab_path = Path(summary["tab"])
        self._last_output_dir = Path(summary["output_dir"])
        if self._tab_path.exists():
            self._tab_preview.load_file(self._tab_path)
            self._save_btn.setEnabled(True)
        self._open_btn.setEnabled(True)
        midi = f"  |  MIDI: {summary['midi_notes']} notes" if summary.get("midi") else ""
        self.statusBar().showMessage(
            f"Done -- {summary['measures']} measures at {summary['tempo_bpm']:.1f} BPM ({summary['instrument']}){midi}"
            f"  |  {self._last_output_dir}")

    def _on_error(self, message: str):
        self._set_busy(False)
        for panel in self._stage_panels.values():
            if panel.is_running():
                panel.set_error(message)
        self.statusBar().showMessage(f"Error: {message}")
        QMessageBox.critical(self, "Pipeline error", message)

    # ------------------------------------------------------------------ misc

    def _save_tab(self):
        if not self._tab_path or not self._tab_path.exists():
            QMessageBox.information(self, "No tab", "Run the pipeline first to generate a tab.")
            return
        dest, _ = QFileDialog.getSaveFileName(self, "Save Tab As", str(self._tab_path),
                                              "Tab files (*.tab);;Text files (*.txt)")
        if dest:
            Path(dest).write_text(self._tab_path.read_text(encoding="utf-8"), encoding="utf-8")
            self.statusBar().showMessage(f"Saved to {dest}")

    def _show_about(self):
        QMessageBox.about(
            self, f"About {APP_TITLE}",
            f"<b>{APP_TITLE}</b> v{VERSION}<br><br>"
            "Converts audio to guitar/bass tab and MIDI<br>using Basic Pitch note detection.<br><br>"
            "Pipeline: Extract -> Process -> Map -> Render -> MIDI<br><br>"
            "See the <b>CLI Reference</b> tab for command-line use.",
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
