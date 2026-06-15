"""CLI reference text and dialog — shown via Help menu."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QPlainTextEdit, QVBoxLayout, QLabel
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt

CLI_REFERENCE = """\
audio2tab — CLI Reference
=========================

All commands run from the audio_to_tab project directory:
  .venv\\Scripts\\python.exe __main__.py <command> [options]

─────────────────────────────────────────────────────────────
FULL PIPELINE (recommended)
─────────────────────────────────────────────────────────────

  run <input_file> [options]

  Run all four stages end-to-end: extract → process → map → render.

  Options:
    --out-dir, -d PATH        Output directory              [default: output]
    --tuning TEXT             Tuning name (see list below)  [default: standard]
    --instrument TEXT         guitar | bass | auto          [default: auto]
    --quantize TEXT           4th | 8th | 16th | 32nd       [default: 8th]
    --measures-per-line INT   Measures per tab line          [default: 4]
    --tempo FLOAT             Override BPM (skip auto-detect)
    --dedup-octaves           Remove octave duplicates (single-instrument stems only)
    --no-intermediates        Delete JSON files after rendering

  Examples:
    python __main__.py run guitar_stem.wav --tuning standard --out-dir output/
    python __main__.py run bass_stem.wav --tuning bass --instrument bass
    python __main__.py run song.mp3 --quantize 16th --measures-per-line 2

─────────────────────────────────────────────────────────────
INDIVIDUAL STAGES
─────────────────────────────────────────────────────────────

  Stage 1 — extract <input_file>
    Audio file → raw note events JSON via Basic Pitch.
    --out PATH               Output JSON             [default: <stem>_notes.json]
    --onset-threshold FLOAT  Onset confidence (0-1)  [default: 0.5]
    --frame-threshold FLOAT  Frame confidence (0-1)  [default: 0.3]
    --min-note-length FLOAT  Min note length (sec)   [default: 0.058]
    --min-freq FLOAT         Min frequency Hz        [default: 40.0]
    --max-freq FLOAT         Max frequency Hz        [default: 2000.0]

  Stage 2 — process <notes_file>
    Raw notes → cleaned, quantized note list JSON.
    --out PATH               Output JSON             [default: <stem>_processed.json]
    --audio PATH             Original audio for tempo detection
    --instrument TEXT        guitar | bass | auto    [default: auto]
    --min-amplitude FLOAT    Drop notes below this   [default: 0.15]
    --min-duration FLOAT     Drop notes shorter (sec)[default: 0.05]
    --merge-gap FLOAT        Merge gap threshold (sec)[default: 0.08]
    --quantize TEXT          4th|8th|16th|32nd       [default: 16th]
    --tempo FLOAT            Override BPM
    --dedup-octaves          Remove octave duplicates

  Stage 3 — map <processed_file>
    Processed notes → (string, fret) assignments JSON.
    --out PATH               Output JSON             [default: <stem>_mapped.json]
    --tuning TEXT            Tuning name             [default: standard]
    --window INT             Fret-hand window size   [default: 5]
    --prefer-high-strings    Use higher/thinner strings (lead guitar feel)

  Stage 4 — render <mapped_file>
    Mapped notes → ASCII tab text file.
    --out PATH               Output .tab file        [default: <stem>.tab]
    --measures-per-line INT  Measures per line       [default: 4]
    --time-sig INT           Beats per measure       [default: 4]

─────────────────────────────────────────────────────────────
AVAILABLE TUNINGS
─────────────────────────────────────────────────────────────

  Guitar:
    standard          E A D G B e  (default)
    drop_d            D A D G B e
    open_g            D G D G B D
    open_d            D A D F# A D
    dadgad            D A D G A D
    half_step_down    Eb Ab Db Gb Bb eb
    full_step_down    D G C F A d

  Bass:
    bass              E A D G  (4-string standard)
    bass_drop_d       D A D G
    bass_5string      B E A D G
    bass_half_step_down  Eb Ab Db Gb

─────────────────────────────────────────────────────────────
TYPICAL WORKFLOWS
─────────────────────────────────────────────────────────────

  Full mix (guitar + bass together):
    python __main__.py run mix_no_drums.mp3 --instrument auto --tuning standard

  Isolated guitar stem from Demucs:
    python __main__.py run guitar_stem.wav --instrument guitar --tuning standard --dedup-octaves

  Isolated bass stem from Demucs:
    python __main__.py run bass_stem.wav --instrument bass --tuning bass --dedup-octaves

  Re-render with different settings (skips slow Stage 1):
    python __main__.py process stem_notes.json --audio stem.wav --quantize 16th --out stem_processed.json
    python __main__.py map stem_processed.json --tuning drop_d --out stem_mapped.json
    python __main__.py render stem_mapped.json --measures-per-line 2 --out stem.tab
"""


class CliReferenceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CLI Reference — audio2tab")
        self.resize(780, 620)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        label = QLabel("Command-line interface — all options available from the terminal.")
        layout.addWidget(label)

        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(CLI_REFERENCE)
        font = QFont("Courier New", 9)
        font.setStyleHint(QFont.StyleHint.Monospace)
        text.setFont(font)
        text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(text)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)
        layout.addWidget(buttons)
