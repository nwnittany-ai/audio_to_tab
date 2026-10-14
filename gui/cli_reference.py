"""CLI reference tab. The text is generated from the real command definitions, so it can never drift from the CLI
(the hand-written version it replaces had stale defaults and was missing several options)."""

from __future__ import annotations

import click
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QPlainTextEdit

from cli.main import cli
from config.defaults import VERSION
from config.tunings import ALL_TUNINGS

_ORDER = ("run", "extract", "process", "map", "render", "midi")

_WORKFLOWS = """\
TYPICAL WORKFLOWS
=================

  Isolated guitar stem (from the stem maker / Demucs):
    audio2tab run guitar_stem.wav --instrument guitar

  Bass stem, tab only:
    audio2tab run bass_stem.wav --tuning bass --instrument bass --no-midi

  Re-do the tab with different settings without repeating the slow Stage 1:
    audio2tab process stem_notes.json --audio stem.wav --quantize 16th --out stem_processed.json
    audio2tab map stem_processed.json --tuning drop_d --out stem_mapped.json
    audio2tab render stem_mapped.json --measures-per-line 2 --out stem.tab

  Make just the MIDI file from already-processed notes:
    audio2tab midi stem_processed.json --timing played --out stem.mid
"""


def build_cli_reference() -> str:
    ctx = click.Context(cli, info_name="audio2tab")
    parts = [f"audio2tab {VERSION} - command-line reference", "=" * 44, "",
             "Run from the project folder with the project's environment:",
             "  .venv\\Scripts\\audio2tab.exe <command> [options]", "",
             cli.get_help(ctx), ""]
    for name in _ORDER:
        command = cli.get_command(ctx, name)
        sub_ctx = click.Context(command, info_name=name, parent=ctx)
        parts += ["-" * 60, f"audio2tab {name}", "-" * 60, command.get_help(sub_ctx), ""]
    parts += ["-" * 60, "AVAILABLE TUNINGS", "-" * 60, "  " + "\n  ".join(sorted(ALL_TUNINGS)), "", _WORKFLOWS]
    return "\n".join(parts)


class CliReferenceView(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont("Courier New", 9)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setPlainText(build_cli_reference())
